"""Deterministic itinerary planner (ADR-0003).

The planner works on an in-memory catalog snapshot, so it is a pure function of its inputs and can be
tested without a database. ``GreedyPlanner`` explores every (country, start date, duration)
combination exhaustively (the space is small) and fills each combination greedily. The three variants
share the algorithm and differ only in how much they weigh cost against quality.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from math import ceil
from typing import Protocol

# --- Catalog snapshot ----------------------------------------------------------------


@dataclass(frozen=True)
class FlightOption:
    id: str
    flight_number: str
    carrier: str
    origin: str
    destination: str
    date: date
    departure_time: str
    arrival_time: str
    price: int  # per person
    seats_left: int


@dataclass(frozen=True)
class HotelOption:
    id: str
    name: str
    stars: int
    neighborhood: str
    nightly: dict[date, tuple[int, int]]  # date -> (price per room, rooms left)


@dataclass(frozen=True)
class ActivityOption:
    id: str
    name: str
    category: str
    description: str
    duration_hours: int
    price: int  # per person
    availability: dict[date, int]  # date -> spots left
    description_ai_generated: bool = False  # provenance of the catalog text, shown in the UI


@dataclass
class CountryCatalog:
    code: str
    name: str
    destination: str
    flights_out: dict[date, list[FlightOption]]  # departure airport -> destination, by date
    flights_back: dict[date, list[FlightOption]]  # destination -> departure airport, by date
    hotels: list[HotelOption]
    activities: list[ActivityOption]


# --- Request and result ----------------------------------------------------------------


@dataclass
class PlanningRequest:
    budget: int
    travelers: int
    start_dates: list[date]
    min_days: int
    max_days: int
    activity_scores: dict[str, float] = field(default_factory=dict)  # 0..1, from RAG + preferences

    @property
    def rooms(self) -> int:
        return rooms_for(self.travelers)


def rooms_for(travelers: int) -> int:
    """Assumption (README): a room holds two people."""
    return ceil(travelers / 2)


@dataclass
class PlannedDay:
    day: int
    date: date
    activity: ActivityOption
    subtotal: int


@dataclass
class PlannedItinerary:
    variant: str
    country_code: str
    start_date: date
    end_date: date
    days: int
    travelers: int
    rooms: int
    outbound: FlightOption
    inbound: FlightOption
    hotel: HotelOption
    hotel_nights: list[tuple[date, int]]  # (night, price per room)
    days_plan: list[PlannedDay]
    budget: int
    quality: float

    @property
    def nights(self) -> int:
        return self.days - 1

    @property
    def flights_cost(self) -> int:
        return (self.outbound.price + self.inbound.price) * self.travelers

    @property
    def hotel_cost(self) -> int:
        return sum(price for _, price in self.hotel_nights) * self.rooms

    @property
    def activities_cost(self) -> int:
        return sum(d.subtotal for d in self.days_plan)

    @property
    def total_price(self) -> int:
        return self.flights_cost + self.hotel_cost + self.activities_cost

    def signature(self) -> tuple:
        return (
            self.country_code,
            self.start_date,
            self.days,
            self.outbound.id,
            self.inbound.id,
            self.hotel.id,
            tuple(d.activity.id for d in self.days_plan),
        )


class Planner(Protocol):
    def plan(self, request: PlanningRequest, catalogs: Iterable[CountryCatalog]) -> list[PlannedItinerary]: ...


# --- Greedy implementation -------------------------------------------------------------


@dataclass(frozen=True)
class Strategy:
    name: str
    hotel_cost_weight: float  # penalty on hotel cost inside a combination
    activity_cost_weight: float  # penalty on activity cost inside a combination
    combination_cost_weight: float | None  # None = minimise total price across combinations


STRATEGIES: tuple[Strategy, ...] = (
    Strategy("economy", hotel_cost_weight=8.0, activity_cost_weight=2.0, combination_cost_weight=None),
    Strategy("balanced", hotel_cost_weight=0.6, activity_cost_weight=0.4, combination_cost_weight=1.0),
    Strategy("premium", hotel_cost_weight=0.0, activity_cost_weight=0.0, combination_cost_weight=0.0),
)

HOTEL_QUALITY_WEIGHT = 0.5


def hotel_quality(stars: int) -> float:
    return (min(max(stars, 1), 5) - 1) / 4


@dataclass
class _Combination:
    """Strategy-independent data for one (country, start date, duration), computed once."""

    catalog: CountryCatalog
    start: date
    days: int
    trip_dates: list[date]
    night_dates: list[date]
    outbound: FlightOption
    inbound: FlightOption
    available: dict[date, list[ActivityOption]]  # sorted by price
    hotels: list[tuple[HotelOption, int]]  # hotels with every night available, with their cost
    min_activities_cost: int


class GreedyPlanner:
    def __init__(self, strategies: tuple[Strategy, ...] = STRATEGIES):
        self.strategies = strategies

    def plan(self, request: PlanningRequest, catalogs: Iterable[CountryCatalog]) -> list[PlannedItinerary]:
        best: dict[str, tuple[tuple, PlannedItinerary]] = {}
        for catalog in catalogs:
            for start in request.start_dates:
                for days in range(request.min_days, request.max_days + 1):
                    combo = _prepare(request, catalog, start, days)
                    if combo is None:
                        continue
                    for strategy in self.strategies:
                        itinerary = _fill(request, combo, strategy)
                        if itinerary is None:
                            continue
                        key = _objective(itinerary, request, strategy)
                        if strategy.name not in best or key > best[strategy.name][0]:
                            best[strategy.name] = (key, itinerary)
        results: list[PlannedItinerary] = []
        seen: set[tuple] = set()
        for strategy in self.strategies:  # keep variant order; drop duplicates (e.g. balanced == premium)
            if strategy.name in best:
                itinerary = best[strategy.name][1]
                if itinerary.signature() not in seen:
                    seen.add(itinerary.signature())
                    results.append(itinerary)
        return results


def _objective(it: PlannedItinerary, req: PlanningRequest, strategy: Strategy) -> tuple:
    if strategy.combination_cost_weight is None:
        return (-it.total_price, it.quality)
    penalty = strategy.combination_cost_weight * req.max_days * it.total_price / req.budget
    return (it.quality - penalty, -it.total_price)


def _prepare(req: PlanningRequest, catalog: CountryCatalog, start: date, days: int) -> _Combination | None:
    travelers, rooms = req.travelers, req.rooms
    end = start + timedelta(days=days - 1)
    outbound = _cheapest(f for f in catalog.flights_out.get(start, []) if f.seats_left >= travelers)
    inbound = _cheapest(f for f in catalog.flights_back.get(end, []) if f.seats_left >= travelers)
    if outbound is None or inbound is None:
        return None
    flights_cost = (outbound.price + inbound.price) * travelers
    if flights_cost > req.budget:
        return None
    trip_dates = [start + timedelta(days=i) for i in range(days)]
    night_dates = trip_dates[:-1]
    available: dict[date, list[ActivityOption]] = {}
    for d in trip_dates:
        options = sorted(
            (a for a in catalog.activities if a.availability.get(d, 0) >= travelers), key=lambda a: a.price
        )
        if not options:
            return None
        available[d] = options
    if len({a.id for options in available.values() for a in options}) < days:
        return None  # not enough distinct activities for one per day
    min_activities_cost = sum(available[d][0].price for d in trip_dates) * travelers
    hotels: list[tuple[HotelOption, int]] = []
    for hotel in catalog.hotels:
        nightly = [hotel.nightly.get(d) for d in night_dates]
        if all(n is not None and n[1] >= rooms for n in nightly):
            hotels.append((hotel, sum(n[0] for n in nightly) * rooms))  # type: ignore[index]
    if not hotels:
        return None
    if flights_cost + min(cost for _, cost in hotels) + min_activities_cost > req.budget:
        return None
    return _Combination(
        catalog, start, days, trip_dates, night_dates, outbound, inbound, available, hotels, min_activities_cost
    )


def _fill(req: PlanningRequest, combo: _Combination, strategy: Strategy) -> PlannedItinerary | None:
    travelers = req.travelers
    nights = combo.days - 1
    scale = req.max_days / req.budget
    remaining = req.budget - (combo.outbound.price + combo.inbound.price) * travelers

    # Hotel: the same hotel every night, leaving room for the cheapest activities.
    best_hotel, best_util, hotel_cost = None, None, 0
    for hotel, cost in combo.hotels:
        if cost + combo.min_activities_cost > remaining:
            continue
        util = hotel_quality(hotel.stars) * nights * HOTEL_QUALITY_WEIGHT - strategy.hotel_cost_weight * scale * cost
        if best_util is None or util > best_util:
            best_hotel, best_util, hotel_cost = hotel, util, cost
    if best_hotel is None:
        return None
    remaining -= hotel_cost

    # Activities: one distinct activity per day. Days with fewer options are filled first. Every pick
    # must leave enough budget for the cheapest still-unused option of each pending day.
    chosen: dict[date, ActivityOption] = {}
    used: set[str] = set()
    for d in sorted(combo.trip_dates, key=lambda x: (len(combo.available[x]), x)):
        pending = [x for x in combo.trip_dates if x not in chosen and x != d]
        # Two cheapest unused options per pending day: picking the cheapest one of a day raises that
        # day's reserve to its second-cheapest price.
        reserve = 0
        extra_if_used: dict[str, int] = {}
        for x in pending:
            first, second = _two_cheapest(combo.available[x], used)
            if first is None:
                return None
            reserve += first.price * travelers
            second_price = second.price if second is not None else 10**9
            extra_if_used[first.id] = extra_if_used.get(first.id, 0) + (second_price - first.price) * travelers
        best_act, best_act_util = None, None
        for act in combo.available[d]:
            if act.id in used:
                continue
            cost = act.price * travelers
            if cost + reserve + extra_if_used.get(act.id, 0) > remaining:
                continue
            util = req.activity_scores.get(act.id, 0.0) - strategy.activity_cost_weight * scale * cost
            if best_act_util is None or util > best_act_util:
                best_act, best_act_util = act, util
        if best_act is None:
            return None
        chosen[d] = best_act
        used.add(best_act.id)
        remaining -= best_act.price * travelers

    days_plan = [
        PlannedDay(day=i + 1, date=d, activity=chosen[d], subtotal=chosen[d].price * travelers)
        for i, d in enumerate(combo.trip_dates)
    ]
    quality = sum(req.activity_scores.get(p.activity.id, 0.0) for p in days_plan)
    quality += hotel_quality(best_hotel.stars) * nights * HOTEL_QUALITY_WEIGHT
    itinerary = PlannedItinerary(
        variant=strategy.name,
        country_code=combo.catalog.code,
        start_date=combo.start,
        end_date=combo.trip_dates[-1],
        days=combo.days,
        travelers=travelers,
        rooms=req.rooms,
        outbound=combo.outbound,
        inbound=combo.inbound,
        hotel=best_hotel,
        hotel_nights=[(d, best_hotel.nightly[d][0]) for d in combo.night_dates],
        days_plan=days_plan,
        budget=req.budget,
        quality=quality,
    )
    if itinerary.total_price > req.budget:  # defensive: the validator checks again anyway
        return None
    return itinerary


def _cheapest(flights: Iterable[FlightOption]) -> FlightOption | None:
    return min(flights, key=lambda f: (f.price, f.departure_time), default=None)


def _two_cheapest(
    options: list[ActivityOption], excluded: set[str]
) -> tuple[ActivityOption | None, ActivityOption | None]:
    """``options`` is sorted by price."""
    found: list[ActivityOption] = []
    for a in options:
        if a.id not in excluded:
            found.append(a)
            if len(found) == 2:
                break
    return (found[0] if found else None, found[1] if len(found) > 1 else None)


# --- Feasibility helpers (used for "consigliami tu" and constraint relaxation) ---------------


def minimum_cost(req: PlanningRequest, catalog: CountryCatalog) -> int | None:
    """Estimated cost of the cheapest trip for the request in one country, ignoring the budget. Used to
    pick feasible countries for "consigliami tu" and to quote relaxations ("da circa X €")."""
    best: int | None = None
    for start in req.start_dates:
        for days in range(req.min_days, req.max_days + 1):
            end = start + timedelta(days=days - 1)
            outbound = _cheapest(f for f in catalog.flights_out.get(start, []) if f.seats_left >= req.travelers)
            inbound = _cheapest(f for f in catalog.flights_back.get(end, []) if f.seats_left >= req.travelers)
            if outbound is None or inbound is None:
                continue
            night_dates = [start + timedelta(days=i) for i in range(days - 1)]
            hotel_costs = []
            for hotel in catalog.hotels:
                nightly = [hotel.nightly.get(d) for d in night_dates]
                if all(n is not None and n[1] >= req.rooms for n in nightly):
                    hotel_costs.append(sum(n[0] for n in nightly) * req.rooms)  # type: ignore[index]
            if not hotel_costs:
                continue
            activity_cost = _cheapest_distinct_activities(catalog, start, days, req.travelers)
            if activity_cost is None:
                continue
            cost = (outbound.price + inbound.price) * req.travelers + min(hotel_costs) + activity_cost
            best = cost if best is None else min(best, cost)
    return best


def _cheapest_distinct_activities(catalog: CountryCatalog, start: date, days: int, travelers: int) -> int | None:
    """Cheapest distinct activity per day, filling the days with fewer options first (greedy estimate)."""
    trip_dates = [start + timedelta(days=i) for i in range(days)]
    options = {
        d: sorted((a for a in catalog.activities if a.availability.get(d, 0) >= travelers), key=lambda a: a.price)
        for d in trip_dates
    }
    used: set[str] = set()
    total = 0
    for d in sorted(trip_dates, key=lambda x: (len(options[x]), x)):
        pick = next((a for a in options[d] if a.id not in used), None)
        if pick is None:
            return None
        used.add(pick.id)
        total += pick.price * travelers
    return total
