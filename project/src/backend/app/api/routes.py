import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import schemas
from app.api.deps import get_conversation_service, get_rate_limiter
from app.auth import get_current_user
from app.config import Settings, get_settings
from app.db import get_session
from app.domain.requirements import CATEGORIES, TripRequirements
from app.logging_setup import conversation_id_var
from app.models import Airport, Booking, Conversation, Country, Itinerary, Message, User
from app.ratelimit import RateLimiter
from app.services import booking as booking_service
from app.services.conversation import ConversationService, InvalidRequest

router = APIRouter(prefix="/api")
log = logging.getLogger(__name__)


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": message})


# --- Presenters ------------------------------------------------------------------------


def _itinerary(it: Itinerary) -> schemas.ItineraryOut:
    return schemas.ItineraryOut.model_validate(
        {**it.view, "id": it.id, "conversation_id": it.conversation_id, "status": it.status}
    )


def _message(m: Message) -> schemas.MessageOut:
    return schemas.MessageOut(
        id=m.id,
        role=m.role,
        content=m.content,
        provider=m.provider,
        model=m.model,  # type: ignore[arg-type]
        ai_generated=m.provider in schemas.AI_PROVIDERS,
        created_at=m.created_at,
        itinerary_ids=m.itinerary_ids or [],
        ui=m.ui,
    )


def _detail(session: Session, conv: Conversation) -> schemas.ConversationDetail:
    req = TripRequirements.model_validate(conv.requirements)
    itineraries = session.scalars(
        select(Itinerary).where(Itinerary.conversation_id == conv.id).order_by(Itinerary.created_at)
    )
    return schemas.ConversationDetail(
        id=conv.id,
        title=conv.title,
        phase=conv.phase,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        requirements=req,
        missing_fields=req.missing_fields(),
        messages=[_message(m) for m in conv.messages],
        itineraries=[_itinerary(it) for it in itineraries],
    )


def _booking(b: Booking) -> schemas.BookingOut:
    return schemas.BookingOut(
        id=b.id,
        status=b.status,
        total_price=b.total_price,
        created_at=b.created_at,  # type: ignore[arg-type]
        cancelled_at=b.cancelled_at,
        itinerary=_itinerary(b.itinerary),
    )


def _own_conversation(session: Session, user: User, conversation_id: str) -> Conversation:
    conv = session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:  # never reveal other users' conversations
        raise _error(404, "not_found", "Conversazione non trovata.")
    conversation_id_var.set(conv.id)
    return conv


# --- Endpoints -------------------------------------------------------------------------


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/me", response_model=schemas.MeOut)
def me(user: User = Depends(get_current_user)) -> schemas.MeOut:
    return schemas.MeOut(id=user.id, username=user.username, email=user.email, name=user.name)


@router.get("/catalog", response_model=schemas.CatalogOut)
def catalog(session: Session = Depends(get_session), _: User = Depends(get_current_user)) -> schemas.CatalogOut:
    countries = session.scalars(select(Country).order_by(Country.name))
    airports = session.scalars(select(Airport).where(Airport.kind == "departure").order_by(Airport.city))
    return schemas.CatalogOut(
        countries=[schemas.CatalogCountry(code=c.code, name=c.name, destination=c.destination) for c in countries],
        departure_airports=[schemas.CatalogAirport(code=a.code, city=a.city, name=a.name) for a in airports],
        categories=[schemas.CatalogCategory(code=k, label=v) for k, v in CATEGORIES.items()],
    )


@router.get("/conversations", response_model=list[schemas.ConversationSummary])
def list_conversations(
    session: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> list[schemas.ConversationSummary]:
    rows = session.scalars(
        select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc())
    )
    return [
        schemas.ConversationSummary(
            id=c.id, title=c.title, phase=c.phase, created_at=c.created_at, updated_at=c.updated_at
        )
        for c in rows
    ]


@router.post("/conversations", response_model=schemas.ConversationDetail, status_code=201)
def create_conversation(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> schemas.ConversationDetail:
    return _detail(session, service.create(user.id))


@router.get("/conversations/{conversation_id}", response_model=schemas.ConversationDetail)
def get_conversation(
    conversation_id: UUID, session: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> schemas.ConversationDetail:
    return _detail(session, _own_conversation(session, user, str(conversation_id)))


@router.post("/conversations/{conversation_id}/messages", response_model=schemas.ConversationDetail)
def send_message(
    conversation_id: UUID,
    body: schemas.SendMessage,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
    settings: Settings = Depends(get_settings),
) -> schemas.ConversationDetail:
    if len(body.content) > settings.max_message_chars:
        raise _error(422, "message_too_long", f"Il messaggio supera i {settings.max_message_chars} caratteri.")
    if not limiter.allow(user.id):
        log.warning("ratelimit.exceeded")
        raise _error(429, "rate_limited", "Troppi messaggi, riprova tra poco.")
    conv = _own_conversation(session, user, str(conversation_id))
    service.handle_message(conv, body.content)
    return _detail(session, conv)


@router.post("/itineraries/{itinerary_id}/select", response_model=schemas.ConversationDetail)
def select_itinerary(
    itinerary_id: UUID,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> schemas.ConversationDetail:
    itinerary = session.get(Itinerary, str(itinerary_id))
    if itinerary is None or itinerary.user_id != user.id:
        raise _error(404, "not_found", "Proposta non trovata.")
    conv = _own_conversation(session, user, itinerary.conversation_id)
    try:
        service.select(conv, itinerary)
    except InvalidRequest as exc:
        raise _error(409, "invalid_state", str(exc)) from exc
    return _detail(session, conv)


@router.post("/bookings", response_model=schemas.BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(
    body: schemas.CreateBooking,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> schemas.BookingOut:
    try:
        booking = booking_service.book(session, user.id, str(body.itinerary_id), str(idempotency_key))
    except booking_service.BookingError as exc:
        if exc.code == "availability_changed":
            itinerary = session.get(Itinerary, str(body.itinerary_id))
            if itinerary is not None:
                itinerary.status = "discarded"
                service.replan_after_conflict(_own_conversation(session, user, itinerary.conversation_id))
        raise _error(exc.status, exc.code, exc.message) from exc
    return _booking(booking)


@router.get("/bookings", response_model=list[schemas.BookingOut])
def list_bookings(
    session: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> list[schemas.BookingOut]:
    rows = session.scalars(select(Booking).where(Booking.user_id == user.id).order_by(Booking.created_at.desc()))
    return [_booking(b) for b in rows]


@router.post("/bookings/{booking_id}/cancel", response_model=schemas.BookingOut)
def cancel_booking(
    booking_id: UUID, session: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> schemas.BookingOut:
    try:
        return _booking(booking_service.cancel(session, user.id, str(booking_id)))
    except booking_service.BookingError as exc:
        raise _error(exc.status, exc.code, exc.message) from exc
