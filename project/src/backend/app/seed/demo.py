"""Pre-loaded conversations for the demo users, so the reviewer finds the interesting cases ready.

They are produced by the real orchestrator with the deterministic mock provider: no API keys needed and
the same result on every machine (the replies carry the MOCK tag, honestly). Tracing is off while
seeding. Seeding runs once per user: a user that already exists is left untouched, so conversations the
reviewer deleted do not come back after a restart.

The user ids match the ids pinned in the Keycloak realm export (infra/keycloak/travel-realm.json).
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import index_factory
from app.config import Settings
from app.domain.phases import Phase
from app.llm.gateway import Gateway
from app.llm.interpreter import Interpreter
from app.llm.mock import MockProvider
from app.models import NAMESPACE, Conversation, Itinerary, User
from app.observability import Observability
from app.services import booking as booking_service
from app.services.conversation import ConversationService

log = logging.getLogger(__name__)

DEMO_USERS = [
    {
        "sub": "4f6c1d2e-8a3b-4c5d-9e7f-1a2b3c4d5e6f",
        "username": "demo",
        "email": "demo@example.com",
        "name": "Demo Viaggiatore",
    },
    {
        "sub": "7a8b9c0d-1e2f-4a3b-8c4d-5e6f7a8b9c0d",
        "username": "reviewer",
        "email": "reviewer@example.com",
        "name": "Reviewer Test",
    },
]

# (title, user messages, action after the messages)
SCRIPTS = [
    (
        "Consigliami tu · giugno",
        ["Consigliami tu: 1500 euro, giugno, una settimana da Roma, viaggio da solo, mi piacciono cultura e cibo"],
        None,
    ),
    (
        "Giappone con 300 € · caso infattibile",
        ["Giappone, 300 euro, 2 persone, aprile, 7 giorni, da Milano, cultura"],
        None,
    ),
    (
        "Barcellona a maggio · prenotata",
        [
            "Vorrei andare in Spagna a maggio",
            "Budget 1800 euro, 5 giorni, partenza da Roma, siamo in 2, ci piacciono cultura e gastronomia",
        ],
        "book",
    ),
    (
        "Grecia ad agosto · proposte e modifica",
        [
            "Siamo in due, budget 2500 euro, vorremmo andare in Grecia ad agosto per 5-7 giorni, partenza da Napoli. "
            "Ci piacciono il mare e la vita notturna.",
            "Nella bilanciata, il giorno 2 vorrei fare qualcosa di diverso",
            "Chi ha vinto i mondiali?",
        ],
        None,
    ),
]


def seed_demo(session: Session, settings: Settings) -> int:
    created = 0
    interpreter = Interpreter(Gateway([MockProvider()]))
    for spec in DEMO_USERS:
        if session.scalar(select(User).where(User.sub == spec["sub"])) is not None:
            continue
        user = User(**spec)
        session.add(user)
        session.commit()
        service = ConversationService(session, interpreter, index_factory, settings)
        service.tracer = Observability(None)
        for title, messages, action in SCRIPTS:
            try:
                conv = service.create(user.id)
                for text in messages:
                    service.handle_message(conv, text)
                if action == "book":
                    _select_and_book(session, service, conv, user)
                conv.title = title
                session.commit()
                created += 1
            except Exception:  # a demo script must never block the application start
                session.rollback()
                log.warning("seed.demo_script_failed", extra={"title": title}, exc_info=True)
    return created


def _select_and_book(session: Session, service: ConversationService, conv: Conversation, user: User) -> None:
    active = {
        it.variant: it
        for it in session.scalars(
            select(Itinerary).where(Itinerary.conversation_id == conv.id, Itinerary.status == "proposed")
        )
    }
    itinerary = active.get("balanced") or next(iter(active.values()), None)
    if itinerary is None:
        return
    service.select(conv, itinerary)  # same path as the "Scegli questa" button
    if conv.phase == Phase.AWAITING_CONFIRMATION:
        key = str(uuid.uuid5(NAMESPACE, f"demo-booking:{user.sub}"))
        booking_service.book(session, user.id, itinerary.id, key)  # same path as "Conferma e prenota"
