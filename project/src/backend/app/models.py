"""ORM models.

- Every id is a UUID (native ``uuid`` column in PostgreSQL, ``str`` in Python). Catalog ids are deterministic
  (uuid5 from the fixture slug or flight number and date): the seed stays reproducible and the vector index
  keeps stable ids. Ids created at runtime are random (uuid4). ISO/IATA codes stay as natural keys.
- All prices are integer euros: budget arithmetic stays exact (no float rounding).
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

NAMESPACE = uuid.UUID("6f1c2a7e-3b9d-4c5e-8a10-2d4f6b8c0e12")  # namespace of the deterministic catalog ids
UUID = Uuid(as_uuid=False)


def new_id() -> str:
    return str(uuid.uuid4())


def catalog_id(kind: str, key: str) -> str:
    """Deterministic id for catalog rows, e.g. catalog_id("activity", "it-valle-dei-templi")."""
    return str(uuid.uuid5(NAMESPACE, f"{kind}:{key}"))


def uuid_pk() -> Mapped[str]:
    return mapped_column(UUID, primary_key=True, default=new_id)


def utcnow() -> datetime:
    return datetime.now(UTC)


# --- Catalog -----------------------------------------------------------------


class CatalogMeta(Base):
    __tablename__ = "catalog_meta"

    id: Mapped[str] = uuid_pk()
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    seed: Mapped[int] = mapped_column(Integer)


class Country(Base):
    __tablename__ = "countries"

    code: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    destination: Mapped[str] = mapped_column(String(120))
    airport_code: Mapped[str] = mapped_column(String(3))
    description: Mapped[str] = mapped_column(Text)


class Airport(Base):
    __tablename__ = "airports"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    city: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16))  # "departure" | "destination"
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)


class Flight(Base):
    __tablename__ = "flights"
    __table_args__ = (Index("ix_flights_route_date", "origin", "destination", "date"),)

    id: Mapped[str] = uuid_pk()
    flight_number: Mapped[str] = mapped_column(String(10))
    carrier: Mapped[str] = mapped_column(String(60))
    origin: Mapped[str] = mapped_column(String(3))
    destination: Mapped[str] = mapped_column(String(3))
    date: Mapped[date] = mapped_column(Date)
    departure_time: Mapped[str] = mapped_column(String(5))
    arrival_time: Mapped[str] = mapped_column(String(8))  # "HH:MM" or "HH:MM+1"
    price: Mapped[int] = mapped_column(Integer)  # per person
    seats_left: Mapped[int] = mapped_column(Integer)


class Hotel(Base):
    __tablename__ = "hotels"

    id: Mapped[str] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(80), unique=True)  # fixture key, human readable
    country_code: Mapped[str] = mapped_column(String(2), index=True)
    name: Mapped[str] = mapped_column(String(120))
    stars: Mapped[int] = mapped_column(Integer)
    neighborhood: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    base_price: Mapped[int] = mapped_column(Integer)


class HotelAvailability(Base):
    __tablename__ = "hotel_availability"

    hotel_id: Mapped[str] = mapped_column(UUID, ForeignKey("hotels.id"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    price: Mapped[int] = mapped_column(Integer)  # per room per night
    rooms_left: Mapped[int] = mapped_column(Integer)


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[str] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(80), unique=True)  # fixture key, human readable
    country_code: Mapped[str] = mapped_column(String(2), index=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(20))
    targets: Mapped[list[str]] = mapped_column(JSON)
    description: Mapped[str] = mapped_column(Text)
    description_ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)  # written with AI, reviewed
    price: Mapped[int] = mapped_column(Integer)  # per person
    duration_hours: Mapped[int] = mapped_column(Integer)
    months: Mapped[list[int]] = mapped_column(JSON)
    closed_weekdays: Mapped[list[int]] = mapped_column(JSON)


class ActivityAvailability(Base):
    __tablename__ = "activity_availability"

    activity_id: Mapped[str] = mapped_column(UUID, ForeignKey("activities.id"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    spots_left: Mapped[int] = mapped_column(Integer)


# --- Users and conversations ---------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = uuid_pk()
    sub: Mapped[str] = mapped_column(String(255), unique=True)
    username: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(UUID, ForeignKey("users.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phase: Mapped[str] = mapped_column(String(32))
    requirements: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # compaction (ADR-0009)
    # Set when a deleted conversation must survive as an empty shell because bookings reference it.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", order_by="Message.seq", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = uuid_pk()
    conversation_id: Mapped[str] = mapped_column(UUID, ForeignKey("conversations.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(16), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    itinerary_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    ui: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


# --- Itineraries and bookings ----------------------------------------------------


class Itinerary(Base):
    __tablename__ = "itineraries"

    id: Mapped[str] = uuid_pk()
    conversation_id: Mapped[str] = mapped_column(UUID, ForeignKey("conversations.id"), index=True)
    user_id: Mapped[str] = mapped_column(UUID, ForeignKey("users.id"), index=True)
    variant: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))  # proposed | selected | booked | discarded
    country_code: Mapped[str] = mapped_column(String(2))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    travelers: Mapped[int] = mapped_column(Integer)
    rooms: Mapped[int] = mapped_column(Integer)
    total_price: Mapped[int] = mapped_column(Integer)
    budget_total: Mapped[int] = mapped_column(Integer)
    view: Mapped[dict] = mapped_column(JSON)  # rendered snapshot returned by the API
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    items: Mapped[list["ItineraryItem"]] = relationship(
        back_populates="itinerary", cascade="all, delete-orphan", order_by="ItineraryItem.position"
    )


class ItineraryItem(Base):
    __tablename__ = "itinerary_items"

    id: Mapped[str] = uuid_pk()
    itinerary_id: Mapped[str] = mapped_column(UUID, ForeignKey("itineraries.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)  # random UUIDs have no order: keep it explicit
    kind: Mapped[str] = mapped_column(String(16))  # flight_out | flight_back | hotel_night | activity
    ref_id: Mapped[str] = mapped_column(UUID)  # id of the flight, hotel or activity
    date: Mapped[date] = mapped_column(Date)
    unit_price: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    subtotal: Mapped[int] = mapped_column(Integer)

    itinerary: Mapped[Itinerary] = relationship(back_populates="items")


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_booking_idempotency"),)

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(UUID, ForeignKey("users.id"), index=True)
    itinerary_id: Mapped[str] = mapped_column(UUID, ForeignKey("itineraries.id"), unique=True)
    status: Mapped[str] = mapped_column(String(16))  # confirmed | cancelled
    total_price: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(UUID)
    price_snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    itinerary: Mapped[Itinerary] = relationship()
