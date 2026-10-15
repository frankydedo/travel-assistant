"""Pre-loaded conversations for the demo users, recorded with the real LLMs (Groq, Gemini).

The conversations were made through the API by a tester acting as a user, and exported with
``python -m app.seed.demo export``. Seeding replays the stored rows (messages with their real provider
tag, itineraries, bookings): no LLM is called and no API key is needed, so the reviewer sees what the real
models wrote, not the mock.

The catalog is deterministic for a given seed month (ADR-0013). When the current catalog was generated
in the same month as the recording, confirmed bookings also take their inventory again and the proposals
can still be modified; otherwise the chats stay readable as history (the cards are stored snapshots).

Seeding runs once per user: a user that already exists is left untouched, so conversations the reviewer
deleted do not come back after a restart. The user ids match the ids pinned in the Keycloak realm.
"""

import json
import logging
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import NAMESPACE, Booking, CatalogMeta, Conversation, Itinerary, ItineraryItem, Message, User
from app.services.booking import _decrement

log = logging.getLogger(__name__)

FIXTURE = Path(__file__).parent / "fixtures" / "demo_conversations.json"

# The reviewer first: its replayed bookings take the inventory, so cancelling them gives it back.
DEMO_USERS = [
    {
        "sub": "7a8b9c0d-1e2f-4a3b-8c4d-5e6f7a8b9c0d",
        "username": "reviewer",
        "email": "reviewer@example.com",
        "name": "Reviewer Test",
    },
    {
        "sub": "4f6c1d2e-8a3b-4c5d-9e7f-1a2b3c4d5e6f",
        "username": "demo",
        "email": "demo@example.com",
        "name": "Demo Viaggiatore",
    },
]


def seed_demo(session: Session, settings: Settings | None = None) -> int:
    if not FIXTURE.exists():
        log.warning("seed.demo_fixture_missing", extra={"path": str(FIXTURE)})
        return 0
    recording = json.loads(FIXTURE.read_text())
    meta = session.scalar(select(CatalogMeta))
    same_catalog = meta is not None and meta.start_date.isoformat() == recording["catalog_start"]
    if not same_catalog:
        log.warning("seed.demo_catalog_mismatch", extra={"recorded": recording["catalog_start"]})
    created = 0
    for spec in DEMO_USERS:
        if session.scalar(select(User).where(User.sub == spec["sub"])) is not None:
            continue
        user = User(**spec)
        session.add(user)
        session.flush()
        for conv in recording["conversations"]:
            _load(session, user, conv, same_catalog)
            created += 1
        session.commit()
    return created


def _load(session: Session, user: User, data: dict, same_catalog: bool) -> None:
    """New ids for every row (the same recording is loaded for each demo user), references remapped."""
    ids: dict[str, str] = {}

    def new_id(old: str) -> str:
        return ids.setdefault(old, str(uuid.uuid5(NAMESPACE, f"demo:{user.sub}:{old}")))

    conv = Conversation(
        id=new_id(data["id"]),
        user_id=user.id,
        title=data["title"],
        phase=data["phase"],
        requirements=data["requirements"],
        created_at=datetime.fromisoformat(data["created_at"]),
    )
    session.add(conv)
    for it in data["itineraries"]:
        itinerary = Itinerary(
            id=new_id(it["id"]),
            conversation_id=conv.id,
            user_id=user.id,
            variant=it["variant"],
            status=it["status"],
            country_code=it["country_code"],
            start_date=date.fromisoformat(it["start_date"]),
            end_date=date.fromisoformat(it["end_date"]),
            travelers=it["travelers"],
            rooms=it["rooms"],
            total_price=it["total_price"],
            budget_total=it["budget_total"],
            view={**it["view"], "id": new_id(it["id"])} if "id" in it["view"] else it["view"],
            created_at=datetime.fromisoformat(it["created_at"]),
        )
        session.add(itinerary)
        for item in it["items"]:
            session.add(ItineraryItem(itinerary_id=itinerary.id, **{**item, "date": date.fromisoformat(item["date"])}))
    session.flush()
    for m in data["messages"]:
        session.add(
            Message(
                conversation_id=conv.id,
                seq=m["seq"],
                role=m["role"],
                content=m["content"],
                provider=m["provider"],
                model=m["model"],
                trace_id=None,  # the traces live in the recording machine's Langfuse
                itinerary_ids=[new_id(i) for i in m["itinerary_ids"]],
                ui=json.loads(_remap(json.dumps(m["ui"]), ids)) if m["ui"] else None,
                created_at=datetime.fromisoformat(m["created_at"]),
            )
        )
    for b in data["bookings"]:
        booking = Booking(
            id=new_id(b["id"]),
            user_id=user.id,
            itinerary_id=new_id(b["itinerary_id"]),
            status=b["status"],
            total_price=b["total_price"],
            idempotency_key=new_id(b["idempotency_key"]),
            price_snapshot=b["price_snapshot"],
            created_at=datetime.fromisoformat(b["created_at"]),
            cancelled_at=datetime.fromisoformat(b["cancelled_at"]) if b["cancelled_at"] else None,
        )
        if booking.status == "confirmed":
            itinerary = next(i for i in data["itineraries"] if i["id"] == b["itinerary_id"])
            held = same_catalog and _hold(session, itinerary["items"])
            # A booking that holds no inventory must not give any back when cancelled (booking.cancel).
            booking.price_snapshot = {**booking.price_snapshot, "inventory_held": held}
        session.add(booking)
    session.flush()


def _hold(session: Session, items: list[dict]) -> bool:
    """Take the inventory of a replayed booking, all items or none (savepoint), as a real booking does."""
    savepoint = session.begin_nested()
    for item in items:
        if not _decrement(session, item["kind"], item["ref_id"], date.fromisoformat(item["date"]), item["quantity"]):
            savepoint.rollback()
            return False
    savepoint.commit()
    return True


def _remap(text: str, ids: dict[str, str]) -> str:
    for old, new in ids.items():
        text = text.replace(old, new)
    return text


def export_demo(session: Session, username: str = "reviewer") -> dict:
    """Recording of a user's conversations, as written to the fixture."""
    user = session.scalar(select(User).where(User.username == username))
    assert user is not None, f"no user {username}"
    meta = session.scalar(select(CatalogMeta))
    conversations = []
    convs = session.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id, Conversation.deleted_at.is_(None))
        .order_by(Conversation.created_at)
    )
    for conv in convs:
        itineraries = session.scalars(select(Itinerary).where(Itinerary.conversation_id == conv.id)).all()
        bookings = session.scalars(select(Booking).where(Booking.itinerary_id.in_([i.id for i in itineraries]))).all()
        conversations.append(
            {
                "id": conv.id,
                "title": conv.title,
                "phase": conv.phase,
                "requirements": conv.requirements,
                "created_at": conv.created_at.isoformat(),
                "messages": [
                    {
                        "seq": m.seq,
                        "role": m.role,
                        "content": m.content,
                        "provider": m.provider,
                        "model": m.model,
                        "itinerary_ids": m.itinerary_ids or [],
                        "ui": m.ui,
                        "created_at": m.created_at.isoformat(),
                    }
                    for m in conv.messages
                ],
                "itineraries": [
                    {
                        "id": i.id,
                        "variant": i.variant,
                        "status": i.status,
                        "country_code": i.country_code,
                        "start_date": i.start_date.isoformat(),
                        "end_date": i.end_date.isoformat(),
                        "travelers": i.travelers,
                        "rooms": i.rooms,
                        "total_price": i.total_price,
                        "budget_total": i.budget_total,
                        "view": i.view,
                        "created_at": i.created_at.isoformat(),
                        "items": [
                            {
                                "position": it.position,
                                "kind": it.kind,
                                "ref_id": it.ref_id,
                                "date": it.date.isoformat(),
                                "unit_price": it.unit_price,
                                "quantity": it.quantity,
                                "subtotal": it.subtotal,
                            }
                            for it in sorted(i.items, key=lambda x: x.position)
                        ],
                    }
                    for i in itineraries
                ],
                "bookings": [
                    {
                        "id": b.id,
                        "itinerary_id": b.itinerary_id,
                        "status": b.status,
                        "total_price": b.total_price,
                        "idempotency_key": b.idempotency_key,
                        "price_snapshot": b.price_snapshot,
                        "created_at": b.created_at.isoformat(),
                        "cancelled_at": b.cancelled_at.isoformat() if b.cancelled_at else None,
                    }
                    for b in bookings
                ],
            }
        )
    return {"catalog_start": meta.start_date.isoformat() if meta else None, "conversations": conversations}


if __name__ == "__main__":
    # The app database is reachable only inside the compose network, so the recording is printed:
    #   docker compose exec -T backend python -m app.seed.demo export \
    #     > src/backend/app/seed/fixtures/demo_conversations.json
    from app.db import session_factory

    if sys.argv[1:2] != ["export"]:
        sys.exit("usage: python -m app.seed.demo export [username] > demo_conversations.json")
    with session_factory()() as s:
        recording = export_demo(s, *sys.argv[2:3])
    print(json.dumps(recording, ensure_ascii=False, indent=1))
    print(f"{len(recording['conversations'])} conversations exported", file=sys.stderr)
