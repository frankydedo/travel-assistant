"""Deterministic modifications of a proposed itinerary, used by the proposal-phase tools (ADR-0001).

The LLM only *asks* for a change ("day 3, something more relaxing"); these pure functions pick the
replacement from the catalog snapshot and return a new ``PlannedItinerary``. The caller validates it and
stores it as a new itinerary: an existing proposal is never edited in place.
"""

from dataclasses import replace
from datetime import date

from app.domain.planner import ActivityOption, CountryCatalog, FlightOption, HotelOption, PlannedDay, PlannedItinerary


class ModificationError(Exception):
    """The change cannot be made within budget and availability: the message is shown to the LLM/user."""


def rehydrate(
    variant: str,
    country_code: str,
    budget: int,
    travelers: int,
    rooms: int,
    items: list[tuple[str, str, date]],  # (kind, ref_id, date) in itinerary order
    catalog: CountryCatalog,
    scores: dict[str, float],
) -> PlannedItinerary:
    """Rebuild a ``PlannedItinerary`` from stored items and a fresh catalog snapshot."""
    flights = {f.id: f for fs in [*catalog.flights_out.values(), *catalog.flights_back.values()] for f in fs}
    hotels = {h.id: h for h in catalog.hotels}
    activities = {a.id: a for a in catalog.activities}
    outbound = inbound = None
    hotel = None
    nights: list[date] = []
    days: list[tuple[date, ActivityOption]] = []
    for kind, ref_id, day in items:
        if kind == "flight_out":
            outbound = flights.get(ref_id)
        elif kind == "flight_back":
            inbound = flights.get(ref_id)
        elif kind == "hotel_night":
            hotel = hotels.get(ref_id)
            nights.append(day)
        elif kind == "activity" and ref_id in activities:
            days.append((day, activities[ref_id]))
    if outbound is None or inbound is None or hotel is None or len(days) != len(nights) + 1:
        raise ModificationError("La proposta non è più disponibile nel catalogo: chiedi una nuova pianificazione.")
    if any(hotel.nightly.get(n) is None for n in nights):
        raise ModificationError("L'hotel di questa proposta non è più disponibile: chiedi una nuova pianificazione.")
    days.sort(key=lambda d: d[0])
    plan = PlannedItinerary(
        variant=variant,
        country_code=country_code,
        start_date=outbound.date,
        end_date=inbound.date,
        days=len(days),
        travelers=travelers,
        rooms=rooms,
        outbound=outbound,
        inbound=inbound,
        hotel=hotel,
        hotel_nights=[(n, hotel.nightly[n][0]) for n in sorted(nights)],
        days_plan=[
            PlannedDay(day=i + 1, date=d, activity=a, subtotal=a.price * travelers) for i, (d, a) in enumerate(days)
        ],
        budget=budget,
        quality=0.0,
    )
    return _with_quality(plan, scores)


def replace_activity(
    plan: PlannedItinerary, day: int, catalog: CountryCatalog, relevance: dict[str, float]
) -> tuple[PlannedItinerary, ActivityOption, ActivityOption]:
    """Swap the activity of ``day`` with the most relevant alternative that is available that day, not
    already in the trip, and keeps the total within budget. ``relevance`` ranks candidates for the
    user's request (from RAG)."""
    if not 1 <= day <= plan.days:
        raise ModificationError(f"Il viaggio dura {plan.days} giorni: scegli un giorno tra 1 e {plan.days}.")
    target = plan.days_plan[day - 1]
    used = {d.activity.id for d in plan.days_plan}
    room = plan.budget - (plan.total_price - target.subtotal)
    candidates = [
        a
        for a in catalog.activities
        if a.id not in used
        and a.availability.get(target.date, 0) >= plan.travelers
        and a.price * plan.travelers <= room
    ]
    if not candidates:
        raise ModificationError(f"Per il giorno {day} non ci sono alternative disponibili che rientrino nel budget.")
    best = max(candidates, key=lambda a: (relevance.get(a.id, 0.0), -a.price))
    new_day = PlannedDay(day=target.day, date=target.date, activity=best, subtotal=best.price * plan.travelers)
    days_plan = [new_day if d.day == day else d for d in plan.days_plan]
    return _with_quality(replace(plan, days_plan=days_plan), relevance), target.activity, best


def replace_hotel(
    plan: PlannedItinerary, direction: str, catalog: CountryCatalog
) -> tuple[PlannedItinerary, HotelOption]:
    """``better``: the cheapest hotel with more stars that fits the budget. ``cheaper``: the best hotel
    (most stars) among those that cost less than the current one."""
    nights = [n for n, _ in plan.hotel_nights]
    current_cost = plan.hotel_cost
    others = []
    for hotel in catalog.hotels:
        if hotel.id == plan.hotel.id:
            continue
        nightly = [hotel.nightly.get(n) for n in nights]
        if all(x is not None and x[1] >= plan.rooms for x in nightly):
            others.append((hotel, sum(x[0] for x in nightly) * plan.rooms))  # type: ignore[index]
    room = plan.budget - (plan.total_price - current_cost)
    if direction == "better":
        options = [(h, c) for h, c in others if h.stars > plan.hotel.stars and c <= room]
        choice = min(options, key=lambda o: (o[1], -o[0].stars), default=None)
    elif direction == "cheaper":
        options = [(h, c) for h, c in others if c < current_cost]
        choice = max(options, key=lambda o: (o[0].stars, -o[1]), default=None)
    else:
        raise ModificationError("Indica se vuoi un hotel migliore o più economico.")
    if choice is None:
        what = "migliore che rientri nel budget" if direction == "better" else "più economico"
        raise ModificationError(f"Non c'è un hotel {what} disponibile per tutte le notti.")
    hotel = choice[0]
    new_plan = replace(plan, hotel=hotel, hotel_nights=[(n, hotel.nightly[n][0]) for n in nights])
    return new_plan, hotel


def _with_quality(plan: PlannedItinerary, scores: dict[str, float]) -> PlannedItinerary:
    return replace(plan, quality=sum(scores.get(d.activity.id, 0.0) for d in plan.days_plan))


__all__ = ["FlightOption", "ModificationError", "rehydrate", "replace_activity", "replace_hotel"]
