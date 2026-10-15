"""Deterministic itinerary planner (ADR-0003).

The planner works on an in-memory catalog snapshot, so it is a pure function of its inputs and can be
tested without a database. ``GreedyPlanner`` explores every (country, start date, duration)
combination exhaustively (the space is small) and fills each combination greedily. The three variants
share the algorithm and differ only in how much they weigh cost against quality.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from math import ceil
from typing import Protocol

from app.domain.schedule import arrival_window, departure_window

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
    budget: int | None  # None = unlimited (ADR-0021): no budget constraint
    travelers: int
    start_dates: list[date]
    min_days: int
    max_days: int
    activity_scores: dict[str, float] = field(default_factory=dict)  # 0..1, from RAG + preferences
    cost_scale: int | None = None  # reference cost that weighs price against quality without a budget
    distinct_countries: bool = False  # "ovunque" (ADR-0022): each variant in a different country if possible

    @property
    def rooms(self) -> int:
        return rooms_for(self.travelers)

    @property
    def scale_base(self) -> int:
        """What a euro is weighed against: the budget, or the reference cost when it is unlimited."""
        return self.budget or self.cost_scale or 1

    def over_budget(self, cost: int) -> bool:
        return self.budget is not None and cost > self.budget


def rooms_for(travelers: int) -> int:
    """Assumption (README): a room holds two people."""
    return ceil(travelers / 2)


@dataclass
class PlannedDay:
    day: int
    date: date
    activity: ActivityOption | None  # None = travel day: the flights leave no time (ADR-0023)
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
    budget: int | None
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
            tuple(d.activity.id if d.activity else None for d in self.days_plan),
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
    available: dict[date, list[ActivityOption]]  # sorted by price; [] on a travel day
    hotels: list[tuple[HotelOption, int]]  # hotels with every night available, with their cost
    min_activities_cost: int


class GreedyPlanner:
    def __init__(self, strategies: tuple[Strategy, ...] = STRATEGIES):
        self.strategies = strategies
        self.missing: dict[str, str] = {}

    def plan(self, request: PlanningRequest, catalogs: Iterable[CountryCatalog]) -> list[PlannedItinerary]:
        combos = [
            combo
            for catalog in catalogs
            for start in request.start_dates
            for days in range(request.min_days, request.max_days + 1)
            if (combo := _prepare(request, catalog, start, days)) is not None
        ]
        if request.budget is None and request.cost_scale is None:
            request = replace(request, cost_scale=self._reference_cost(request, combos))
        # Best itinerary per strategy and per country: "ovunque" may need the runner-up country.
        best: dict[str, dict[str, tuple[tuple, PlannedItinerary]]] = {}
        for combo in combos:
            for strategy in self.strategies:
                itinerary = _fill(request, combo, strategy)
                if itinerary is None:
                    continue
                key = _objective(itinerary, request, strategy)
                per_country = best.setdefault(strategy.name, {})
                if combo.catalog.code not in per_country or key > per_country[combo.catalog.code][0]:
                    per_country[combo.catalog.code] = (key, itinerary)
        results: list[PlannedItinerary] = []
        seen: dict[tuple, str] = {}
        used_countries: set[str] = set()
        self.missing = {}  # variant -> why it is not proposed, for the reply (written by code)
        for strategy in self.strategies:  # keep variant order; drop duplicates (e.g. balanced == premium)
            ranked = [it for _, it in sorted(best.get(strategy.name, {}).values(), key=lambda kv: kv[0], reverse=True)]
            if not ranked:
                continue
            pick = ranked[0]
            if request.distinct_countries:
                pick = next((it for it in ranked if it.country_code not in used_countries), pick)
            if pick.signature() in seen:
                self.missing[strategy.name] = f"same_as:{seen[pick.signature()]}"
            else:
                seen[pick.signature()] = strategy.name
                used_countries.add(pick.country_code)
                results.append(pick)
        return results

    def _reference_cost(self, request: PlanningRequest, combos: list["_Combination"]) -> int | None:
        """Unlimited budget (ADR-0022): price is weighed against the cost of the quality-only trip, so the
        balanced variant really sits between the cheapest and the best one. The quality-only strategy does
        not look at prices, so its plan does not depend on this reference."""
        quality_only = next((s for s in self.strategies if s.combination_cost_weight == 0.0), None)
        if quality_only is None:
            return None
        best: tuple[tuple, PlannedItinerary] | None = None
        for combo in combos:
            itinerary = _fill(request, combo, quality_only)
            if itinerary is not None:
                key = _objective(itinerary, request, quality_only)
                if best is None or key > best[0]:
                    best = (key, itinerary)
        return best[1].total_price if best else None


def _objective(it: PlannedItinerary, req: PlanningRequest, strategy: Strategy) -> tuple:
    if strategy.combination_cost_weight is None:
        return (-it.total_price, it.quality)
    penalty = strategy.combination_cost_weight * req.max_days * it.total_price / req.scale_base
    return (it.quality - penalty, -it.total_price)


def _prepare(req: PlanningRequest, catalog: CountryCatalog, start: date, days: int) -> _Combination | None:
    """ADR-0023: flights that leave time for an activity on the travel days first; if that combination
    does not fit the budget (or does not exist), the cheapest flights, with declared travel days."""
    return _build(req, catalog, start, days, prefer_compatible=True) or _build(
        req, catalog, start, days, prefer_compatible=False
    )


def _build(
    req: PlanningRequest, catalog: CountryCatalog, start: date, days: int, prefer_compatible: bool
) -> _Combination | None:
    travelers, rooms = req.travelers, req.rooms
    end = start + timedelta(days=days - 1)
    trip_dates = [start + timedelta(days=i) for i in range(days)]
    night_dates = trip_dates[:-1]
    available: dict[date, list[ActivityOption]] = {}
    for d in trip_dates:
        available[d] = sorted(
            (a for a in catalog.activities if a.availability.get(d, 0) >= travelers), key=lambda a: a.price
        )
        if not available[d] and d not in (start, end):
            return None
    outbound = _pick_flight(
        catalog.flights_out.get(start, []), travelers, available[start], _arrival_hours, prefer_compatible
    )
    inbound = _pick_flight(
        catalog.flights_back.get(end, []), travelers, available[end], _departure_hours, prefer_compatible
    )
    if outbound is None or inbound is None:
        return None
    shortest = min((a.duration_hours for a in catalog.activities), default=0)
    for day, hours in ((start, _arrival_hours(outbound)), (end, _departure_hours(inbound))):
        fitting = [a for a in available[day] if a.duration_hours <= hours]
        if not fitting and hours >= shortest:
            return None  # the flights leave time: an empty day here would not be a travel day
        available[day] = fitting
    flights_cost = (outbound.price + inbound.price) * travelers
    if req.over_budget(flights_cost):
        return None
    activity_days = [d for d in trip_dates if available[d]]
    if len({a.id for d in activity_days for a in available[d]}) < len(activity_days):
        return None  # not enough distinct activities for one per day
    min_activities_cost = sum(available[d][0].price for d in activity_days) * travelers
    hotels: list[tuple[HotelOption, int]] = []
    for hotel in catalog.hotels:
        nightly = [hotel.nightly.get(d) for d in night_dates]
        if all(n is not None and n[1] >= rooms for n in nightly):
            hotels.append((hotel, sum(n[0] for n in nightly) * rooms))  # type: ignore[index]
    if not hotels:
        return None
    if req.over_budget(flights_cost + min(cost for _, cost in hotels) + min_activities_cost):
        return None
    return _Combination(
        catalog, start, days, trip_dates, night_dates, outbound, inbound, available, hotels, min_activities_cost
    )


def _arrival_hours(flight: FlightOption) -> float:
    return arrival_window(flight.arrival_time)


def _departure_hours(flight: FlightOption) -> float:
    return departure_window(flight.departure_time)


def _pick_flight(
    flights, travelers: int, activities: list[ActivityOption], free_hours, prefer_compatible: bool
) -> FlightOption | None:
    with_seats = [f for f in flights if f.seats_left >= travelers]
    if not prefer_compatible:
        return _cheapest(with_seats)
    shortest = min((a.duration_hours for a in activities), default=None)
    compatible = [f for f in with_seats if shortest is not None and shortest <= free_hours(f)]
    return _cheapest(compatible) or _cheapest(with_seats)


def _fill(req: PlanningRequest, combo: _Combination, strategy: Strategy) -> PlannedItinerary | None:
    travelers = req.travelers
    nights = combo.days - 1
    scale = req.max_days / req.scale_base
    budget = req.budget if req.budget is not None else 10**12  # unlimited: never the binding constraint
    remaining = budget - (combo.outbound.price + combo.inbound.price) * travelers

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
    activity_days = [d for d in combo.trip_dates if combo.available[d]]
    for d in sorted(activity_days, key=lambda x: (len(combo.available[x]), x)):
        pending = [x for x in activity_days if x not in chosen and x != d]
        # Two cheapest unused options per pending day: picking the cheapest one of a day raises that
        # day's reserve to its second-cheapest price.
        reserve = 0
        extra_if_used: dict[str, int] = {}
        starving: set[str] = set()  # the last unused option of a pending day: taking it leaves that day empty
        for x in pending:
            first, second = _two_cheapest(combo.available[x], used)
            if first is None:
                return None
            reserve += first.price * travelers
            if second is None:
                starving.add(first.id)
            else:
                extra_if_used[first.id] = extra_if_used.get(first.id, 0) + (second.price - first.price) * travelers
        best_act, best_act_util = None, None
        for act in combo.available[d]:
            if act.id in used or act.id in starving:
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
        PlannedDay(
            day=i + 1,
            date=d,
            activity=chosen.get(d),
            subtotal=chosen[d].price * travelers if d in chosen else 0,
        )
        for i, d in enumerate(combo.trip_dates)
    ]
    quality = sum(req.activity_scores.get(p.activity.id, 0.0) for p in days_plan if p.activity)
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
    if req.over_budget(itinerary.total_price):  # defensive: the validator checks again anyway
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
    unbounded = replace(req, budget=None)
    best: int | None = None
    for start in req.start_dates:
        for days in range(req.min_days, req.max_days + 1):
            combo = _build(unbounded, catalog, start, days, prefer_compatible=False)  # the true minimum
            if combo is None:
                continue
            activity_cost = _cheapest_distinct_activities(combo, req.travelers)
            if activity_cost is None:
                continue
            flights = (combo.outbound.price + combo.inbound.price) * req.travelers
            cost = flights + min(c for _, c in combo.hotels) + activity_cost
            best = cost if best is None else min(best, cost)
    return best


def _cheapest_distinct_activities(combo: _Combination, travelers: int) -> int | None:
    """Cheapest distinct activity per activity day, filling the days with fewer options first (greedy)."""
    activity_days = [d for d in combo.trip_dates if combo.available[d]]
    used: set[str] = set()
    total = 0
    for d in sorted(activity_days, key=lambda x: (len(combo.available[x]), x)):
        pick = next((a for a in combo.available[d] if a.id not in used), None)
        if pick is None:
            return None
        used.add(pick.id)
        total += pick.price * travelers
    return total
