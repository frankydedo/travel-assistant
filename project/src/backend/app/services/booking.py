"""Booking (ADR-0006): explicit confirmation, one transaction, idempotency, price snapshot.

The endpoint receives only an itinerary id and an idempotency key. Prices and items are read from the
database, the user comes from the authenticated session, availability is re-validated and inventory is
decremented with conditional updates, so concurrent bookings cannot oversell.
"""

import logging
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalog import SqlInventory
from app.domain.phases import Phase, change_phase
from app.domain.validator import DraftItem, ItineraryDraft, validate
from app.models import (
    ActivityAvailability,
    Booking,
    Conversation,
    Flight,
    HotelAvailability,
    Itinerary,
    Message,
    utcnow,
)
from app.textfmt import eur, period_it

log = logging.getLogger(__name__)


class BookingError(Exception):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class _Conflict(Exception):
    pass


def _draft(itinerary: Itinerary, departure_airport: str) -> ItineraryDraft:
    return ItineraryDraft(
        country_code=itinerary.country_code,
        departure_airport=departure_airport,
        start_date=itinerary.start_date,
        end_date=itinerary.end_date,
        travelers=itinerary.travelers,
        rooms=itinerary.rooms,
        budget=itinerary.budget_total,
        items=tuple(DraftItem(i.kind, i.ref_id, i.date, i.unit_price, i.quantity) for i in itinerary.items),
    )


def _decrement(session: Session, kind: str, ref_id: str, day: date, quantity: int, sign: int = 1) -> int:
    """Conditional atomic update: decrement only if enough inventory is left. Returns affected rows."""
    delta = quantity * sign
    if kind in ("flight_out", "flight_back"):
        stmt = update(Flight).where(Flight.id == ref_id).values(seats_left=Flight.seats_left - delta)
        if sign > 0:
            stmt = stmt.where(Flight.seats_left >= quantity)
    elif kind == "hotel_night":
        stmt = (
            update(HotelAvailability)
            .where(HotelAvailability.hotel_id == ref_id, HotelAvailability.date == day)
            .values(rooms_left=HotelAvailability.rooms_left - delta)
        )
        if sign > 0:
            stmt = stmt.where(HotelAvailability.rooms_left >= quantity)
    elif kind == "activity":
        stmt = (
            update(ActivityAvailability)
            .where(ActivityAvailability.activity_id == ref_id, ActivityAvailability.date == day)
            .values(spots_left=ActivityAvailability.spots_left - delta)
        )
        if sign > 0:
            stmt = stmt.where(ActivityAvailability.spots_left >= quantity)
    else:
        raise ValueError(kind)
    return session.execute(stmt, execution_options={"synchronize_session": False}).rowcount


def book(session: Session, user_id: str, itinerary_id: str, idempotency_key: str) -> Booking:
    existing = session.scalar(
        select(Booking).where(Booking.user_id == user_id, Booking.idempotency_key == idempotency_key)
    )
    if existing is not None:
        if existing.itinerary_id != itinerary_id:
            raise BookingError("idempotency_mismatch", "Chiave di idempotenza già usata per un'altra proposta.", 422)
        log.info("booking.idempotent_replay", extra={"booking_id": existing.id})
        return existing  # a retry of a request that already succeeded

    itinerary = session.get(Itinerary, itinerary_id)
    if itinerary is None or itinerary.user_id != user_id:
        raise BookingError("not_found", "Proposta non trovata.", 404)
    conversation = session.get(Conversation, itinerary.conversation_id)
    assert conversation is not None
    if itinerary.status != "selected" or conversation.phase != Phase.AWAITING_CONFIRMATION:
        raise BookingError("invalid_state", "Questa proposta non è in attesa di conferma.", 409)

    draft = _draft(itinerary, itinerary.view["flights"]["outbound"]["origin"])
    try:
        errors = validate(draft, SqlInventory(session))
        if errors:
            raise _Conflict(errors)
        for item in draft.items:
            if _decrement(session, item.kind, item.ref_id, item.date, item.quantity) != 1:
                raise _Conflict([f"{item.kind} {item.ref_id} {item.date}: sold out meanwhile"])
        booking = Booking(
            user_id=user_id,
            itinerary_id=itinerary.id,
            status="confirmed",
            total_price=draft.total_price,
            idempotency_key=idempotency_key,
            price_snapshot={
                "total": draft.total_price,
                "items": [
                    {
                        "kind": i.kind,
                        "ref_id": i.ref_id,
                        "date": i.date.isoformat(),
                        "unit_price": i.unit_price,
                        "quantity": i.quantity,
                        "subtotal": i.subtotal,
                    }
                    for i in draft.items
                ],
            },
        )
        session.add(booking)
        itinerary.status = "booked"
        change_phase(conversation, Phase.BOOKED)
        conversation.messages.append(
            Message(
                conversation_id=conversation.id,
                seq=len(conversation.messages) + 1,
                role="assistant",
                content=(
                    f"Prenotazione confermata: {itinerary.view['destination']} "
                    f"{period_it(itinerary.view['start_date'], itinerary.view['end_date'])}, totale "
                    f"{eur(draft.total_price)}. La trovi nella pagina Prenotazioni. Buon viaggio!"
                ),
                provider="SYSTEM",
                itinerary_ids=[itinerary.id],
            )
        )
        session.commit()
        log.info(
            "booking.confirmed",
            extra={"booking_id": booking.id, "itinerary_id": itinerary.id, "total_price": booking.total_price},
        )
        return booking
    except _Conflict as conflict:
        session.rollback()
        log.warning("booking.conflict", extra={"itinerary_id": itinerary_id, "errors": conflict.args[0][:5]})
        raise BookingError(
            "availability_changed",
            "La disponibilità è cambiata nel frattempo: ho preparato nuove proposte in chat.",
            409,
        ) from None
    except IntegrityError:
        # Concurrent request with the same idempotency key: return the one that won.
        session.rollback()
        winner = session.scalar(
            select(Booking).where(Booking.user_id == user_id, Booking.idempotency_key == idempotency_key)
        )
        if winner is None:
            raise
        return winner


def cancel(session: Session, user_id: str, booking_id: str) -> Booking:
    booking = session.get(Booking, booking_id)
    if booking is None or booking.user_id != user_id:
        raise BookingError("not_found", "Prenotazione non trovata.", 404)
    if booking.status == "cancelled":
        return booking
    if (booking.price_snapshot or {}).get("inventory_held", True):  # a replayed demo booking may hold none
        for item in booking.itinerary.items:
            _decrement(session, item.kind, item.ref_id, item.date, item.quantity, sign=-1)  # give inventory back
    booking.status = "cancelled"
    booking.cancelled_at = utcnow()
    booking.itinerary.status = "discarded"
    _reopen(session, booking)
    session.commit()
    log.info("booking.cancelled", extra={"booking_id": booking.id})
    return booking


def _reopen(session: Session, booking: Booking) -> None:
    """ADR-0024: a cancelled booking reopens its conversation, so a new message is not answered with
    "questo viaggio è già prenotato". A fixed message written by code says what happened."""
    conv = session.get(Conversation, booking.itinerary.conversation_id)
    if conv is None or conv.deleted_at is not None or conv.phase != Phase.BOOKED:
        return  # a deleted conversation stays a hidden shell
    others = session.scalars(
        select(Itinerary).where(Itinerary.conversation_id == conv.id, Itinerary.status == "proposed")
    ).all()
    change_phase(conv, Phase.PROPOSING if others else Phase.COLLECTING_REQUIREMENTS)
    text = (
        f"Prenotazione annullata ({eur(booking.total_price)}): voli, hotel e attività sono di nuovo disponibili. "
        + (
            "Le altre proposte sono ancora qui: scegline una o dimmi cosa cambiare."
            if others
            else "Se vuoi, preparo nuove proposte con gli stessi requisiti: scrivimi pure, anche solo «ok»."
        )
    )
    conv.messages.append(Message(seq=len(conv.messages) + 1, role="assistant", content=text, provider="SYSTEM"))
