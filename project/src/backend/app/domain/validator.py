"""Deterministic itinerary validator (ADR-0003, ADR-0006).

Independent from the planner on purpose: it re-reads fresh inventory through ``InventoryReader`` and
checks budget, availability, IDs and prices. It runs before an itinerary reaches the user and again at
booking time, so a planner bug or an inventory change is caught.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

from app.domain.planner import PlannedItinerary


@dataclass(frozen=True)
class DraftItem:
    kind: str  # flight_out | flight_back | hotel_night | activity
    ref_id: str
    date: date
    unit_price: int
    quantity: int

    @property
    def subtotal(self) -> int:
        return self.unit_price * self.quantity


@dataclass(frozen=True)
class ItineraryDraft:
    country_code: str
    departure_airport: str
    start_date: date
    end_date: date
    travelers: int
    rooms: int
    budget: int
    items: tuple[DraftItem, ...]

    @property
    def total_price(self) -> int:
        return sum(i.subtotal for i in self.items)


@dataclass(frozen=True)
class FlightFacts:
    origin: str
    destination: str
    date: date
    price: int
    seats_left: int


class InventoryReader(Protocol):
    def destination_airport(self, country_code: str) -> str | None: ...
    def flight(self, flight_id: str) -> FlightFacts | None: ...
    def hotel_night(self, hotel_id: str, night: date) -> tuple[int, int] | None: ...  # (price, rooms_left)
    def activity(self, activity_id: str, day: date) -> tuple[int, int] | None: ...  # (price, spots_left)


def draft_from_plan(plan: PlannedItinerary, departure_airport: str) -> ItineraryDraft:
    items: list[DraftItem] = [
        DraftItem("flight_out", plan.outbound.id, plan.outbound.date, plan.outbound.price, plan.travelers),
        DraftItem("flight_back", plan.inbound.id, plan.inbound.date, plan.inbound.price, plan.travelers),
    ]
    items += [DraftItem("hotel_night", plan.hotel.id, night, price, plan.rooms) for night, price in plan.hotel_nights]
    items += [DraftItem("activity", d.activity.id, d.date, d.activity.price, plan.travelers) for d in plan.days_plan]
    return ItineraryDraft(
        country_code=plan.country_code,
        departure_airport=departure_airport,
        start_date=plan.start_date,
        end_date=plan.end_date,
        travelers=plan.travelers,
        rooms=plan.rooms,
        budget=plan.budget,
        items=tuple(items),
    )


def validate(draft: ItineraryDraft, inventory: InventoryReader) -> list[str]:
    """Return the list of violations (empty means valid)."""
    errors: list[str] = []
    by_kind: dict[str, list[DraftItem]] = {}
    for item in draft.items:
        by_kind.setdefault(item.kind, []).append(item)
        if item.unit_price < 0 or item.quantity <= 0:
            errors.append(f"{item.kind} {item.ref_id}: invalid price or quantity")

    if draft.total_price > draft.budget:
        errors.append(f"total {draft.total_price} exceeds budget {draft.budget}")
    if draft.end_date < draft.start_date:
        errors.append("end date before start date")
    days = (draft.end_date - draft.start_date).days + 1
    trip_dates = [draft.start_date + timedelta(days=i) for i in range(days)]

    destination = inventory.destination_airport(draft.country_code)
    if destination is None:
        errors.append(f"unknown country {draft.country_code}")

    # Flights: exactly one each way, on the right dates and routes, with seats and the stored price.
    for kind, expected_date, origin, dest in (
        ("flight_out", draft.start_date, draft.departure_airport, destination),
        ("flight_back", draft.end_date, destination, draft.departure_airport),
    ):
        flights = by_kind.get(kind, [])
        if len(flights) != 1:
            errors.append(f"expected exactly one {kind}, found {len(flights)}")
            continue
        item = flights[0]
        facts = inventory.flight(item.ref_id)
        if facts is None:
            errors.append(f"{kind} {item.ref_id}: unknown flight")
            continue
        if (facts.origin, facts.destination) != (origin, dest):
            errors.append(f"{kind} {item.ref_id}: wrong route {facts.origin}->{facts.destination}")
        if facts.date != expected_date or item.date != expected_date:
            errors.append(f"{kind} {item.ref_id}: wrong date")
        if facts.price != item.unit_price:
            errors.append(f"{kind} {item.ref_id}: price changed ({item.unit_price} -> {facts.price})")
        if facts.seats_left < draft.travelers or item.quantity != draft.travelers:
            errors.append(f"{kind} {item.ref_id}: not enough seats")

    # Hotel: one hotel, one night for each night of the trip, enough rooms, stored price.
    nights = by_kind.get("hotel_night", [])
    if len({n.ref_id for n in nights}) > 1:
        errors.append("more than one hotel")
    if sorted(n.date for n in nights) != trip_dates[:-1]:
        errors.append("hotel nights do not cover every night of the trip")
    for night in nights:
        facts = inventory.hotel_night(night.ref_id, night.date)
        if facts is None:
            errors.append(f"hotel {night.ref_id}: not available on {night.date}")
            continue
        price, rooms_left = facts
        if price != night.unit_price:
            errors.append(f"hotel {night.ref_id} {night.date}: price changed ({night.unit_price} -> {price})")
        if rooms_left < draft.rooms or night.quantity != draft.rooms:
            errors.append(f"hotel {night.ref_id} {night.date}: not enough rooms")

    # Activities: one distinct activity per day, available, with enough spots and the stored price.
    activities = by_kind.get("activity", [])
    if sorted(a.date for a in activities) != trip_dates:
        errors.append("activities do not cover every day exactly once")
    if len({a.ref_id for a in activities}) != len(activities):
        errors.append("the same activity is scheduled twice")
    for act in activities:
        facts = inventory.activity(act.ref_id, act.date)
        if facts is None:
            errors.append(f"activity {act.ref_id}: not available on {act.date}")
            continue
        price, spots_left = facts
        if price != act.unit_price:
            errors.append(f"activity {act.ref_id}: price changed ({act.unit_price} -> {price})")
        if spots_left < draft.travelers or act.quantity != draft.travelers:
            errors.append(f"activity {act.ref_id} {act.date}: not enough spots")

    return errors
