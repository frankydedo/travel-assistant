"""Rename and delete conversations.

Deleting really deletes: messages and proposals that were not booked are removed. A confirmed booking
must keep its itinerary (and the itinerary its conversation), so in that case only an emptied, hidden
conversation row remains; the booking stays visible in the bookings dashboard.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.requirements import TripRequirements
from app.models import Booking, Conversation, Itinerary, utcnow

log = logging.getLogger(__name__)


def rename(session: Session, conv: Conversation, title: str) -> Conversation:
    conv.title = title
    session.commit()
    log.info("conversation.renamed")
    return conv


def delete(session: Session, conv: Conversation) -> None:
    booked = set(
        session.scalars(
            select(Booking.itinerary_id)
            .join(Itinerary, Booking.itinerary_id == Itinerary.id)
            .where(Itinerary.conversation_id == conv.id)
        )
    )
    for itinerary in session.scalars(select(Itinerary).where(Itinerary.conversation_id == conv.id)):
        if itinerary.id not in booked:
            session.delete(itinerary)  # items cascade
    if booked:
        conv.messages.clear()  # delete-orphan: the messages are deleted
        conv.title = None
        conv.summary = None
        conv.requirements = TripRequirements().model_dump(mode="json")
        conv.deleted_at = utcnow()
    else:
        session.delete(conv)  # messages cascade
    session.commit()
    log.info("conversation.deleted", extra={"kept_for_bookings": bool(booked)})
