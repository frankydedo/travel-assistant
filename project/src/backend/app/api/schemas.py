"""API response/request models (the contract shared with the frontend)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.domain.requirements import TripRequirements
from app.llm.registry import AI_PROVIDERS  # noqa: F401  (re-exported for the presenters)

Provider = Literal["GEMINI", "GROQ", "MOCK", "SYSTEM"]


class MessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    provider: Provider | None
    model: str | None
    ai_generated: bool
    trace_url: str | None = None  # link to the turn's trace in Langfuse
    created_at: datetime
    itinerary_ids: list[str]
    ui: dict | None


class FlightOut(BaseModel):
    id: str
    flight_number: str
    carrier: str
    origin: str
    destination: str
    date: str
    departure_time: str
    arrival_time: str
    price_per_person: int
    subtotal: int


class FlightsOut(BaseModel):
    outbound: FlightOut
    return_: FlightOut = Field(alias="return", serialization_alias="return")


class HotelOut(BaseModel):
    id: str
    name: str
    stars: int
    neighborhood: str
    nights: int
    price_per_night_avg: int
    subtotal: int


class ActivityOut(BaseModel):
    id: str
    name: str
    category: str
    description: str
    description_ai_generated: bool = False
    duration_hours: int
    price_per_person: int
    subtotal: int


class DayOut(BaseModel):
    day: int
    date: str
    travel_day: bool = False  # ADR-0023: the flights leave no time for an activity
    travel_note: str | None = None  # first/last day: arrival or departure time
    activity: ActivityOut | None


class CostBreakdown(BaseModel):
    flights: int
    hotel: int
    activities: int


class ItineraryOut(BaseModel):
    id: str
    conversation_id: str
    variant: Literal["economy", "balanced", "premium"]
    status: Literal["proposed", "selected", "booked", "discarded"]
    country_code: str
    country_name: str
    destination: str
    start_date: str
    end_date: str
    days: int
    nights: int
    travelers: int
    rooms: int
    total_price: int
    budget_total: int | None
    cost_breakdown: CostBreakdown
    flights: FlightsOut
    hotel: HotelOut
    days_plan: list[DayOut]


class ConversationSummary(BaseModel):
    id: str
    title: str | None
    phase: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationSummary):
    requirements: TripRequirements
    missing_fields: list[str]
    messages: list[MessageOut]
    itineraries: list[ItineraryOut]


class RenameConversation(BaseModel):
    title: str

    @field_validator("title")
    @classmethod
    def _clean(cls, value: str) -> str:
        value = " ".join(value.split())
        if not 1 <= len(value) <= 80:
            raise ValueError("il titolo deve avere tra 1 e 80 caratteri")
        return value


class SendMessage(BaseModel):
    content: str = Field(min_length=1)


class CreateBooking(BaseModel):
    itinerary_id: UUID


class BookingOut(BaseModel):
    id: str
    status: Literal["confirmed", "cancelled"]
    total_price: int
    created_at: datetime
    cancelled_at: datetime | None
    itinerary: ItineraryOut


class CatalogCountry(BaseModel):
    code: str
    name: str
    destination: str


class CatalogAirport(BaseModel):
    code: str
    city: str
    name: str


class CatalogCategory(BaseModel):
    code: str
    label: str


class CatalogOut(BaseModel):
    countries: list[CatalogCountry]
    departure_airports: list[CatalogAirport]
    categories: list[CatalogCategory]


class MeOut(BaseModel):
    id: str
    username: str
    email: str | None
    name: str | None
