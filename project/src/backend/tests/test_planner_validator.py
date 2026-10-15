from datetime import date, timedelta

from app.domain.planner import (
    ActivityOption,
    CountryCatalog,
    FlightOption,
    GreedyPlanner,
    HotelOption,
    PlanningRequest,
    minimum_cost,
)
from app.domain.validator import FlightFacts, draft_from_plan, validate

START = date.today() + timedelta(days=30)
DAYS = [START + timedelta(days=i) for i in range(20)]


def make_catalog(activity_spots: int = 10) -> CountryCatalog:
    out = {
        d: [FlightOption(f"out-{i}", f"AB{i}", "Airone Blu", "FCO", "BCN", d, "08:00", "10:00", 80 + i, 20)]
        for i, d in enumerate(DAYS)
    }
    back = {
        d: [FlightOption(f"back-{i}", f"AB{i}", "Airone Blu", "BCN", "FCO", d, "18:00", "20:00", 90, 20)]
        for i, d in enumerate(DAYS)
    }
    hotels = [
        HotelOption("h2", "Ostello", 2, "Raval", {d: (60, 5) for d in DAYS}),
        HotelOption("h3", "Medio", 3, "Gracia", {d: (110, 5) for d in DAYS}),
        HotelOption("h5", "Lusso", 5, "Eixample", {d: (320, 5) for d in DAYS}),
    ]
    activities = [
        ActivityOption(f"a{i}", f"Attività {i}", "cultura", "", 2, price, {d: activity_spots for d in DAYS})
        for i, price in enumerate([0, 0, 10, 15, 20, 30, 45, 60, 80, 120])
    ]
    return CountryCatalog("ES", "Spagna", "Barcellona", out, back, hotels, activities)


def request(budget: int, min_days: int = 4, max_days: int = 6, travelers: int = 2) -> PlanningRequest:
    scores = {f"a{i}": s for i, s in enumerate([0.1, 0.2, 0.9, 0.3, 0.8, 0.4, 0.95, 0.5, 0.7, 1.0])}
    return PlanningRequest(budget, travelers, DAYS[:5], min_days, max_days, scores)


class FakeInventory:
    def __init__(self, catalog: CountryCatalog):
        self.flights = {f.id: f for fs in [*catalog.flights_out.values(), *catalog.flights_back.values()] for f in fs}
        self.hotels = {h.id: h for h in catalog.hotels}
        self.activities = {a.id: a for a in catalog.activities}

    def destination_airport(self, country_code):
        return "BCN" if country_code == "ES" else None

    def flight(self, flight_id):
        f = self.flights.get(flight_id)
        return (
            FlightFacts(f.origin, f.destination, f.date, f.price, f.seats_left, f.departure_time, f.arrival_time)
            if f
            else None
        )

    def hotel_night(self, hotel_id, night):
        return self.hotels[hotel_id].nightly.get(night)

    def activity_duration(self, activity_id):
        return self.activities[activity_id].duration_hours

    def activity(self, activity_id, day):
        a = self.activities[activity_id]
        return (a.price, a.availability[day]) if day in a.availability else None


def test_three_variants_within_budget_and_valid():
    catalog = make_catalog()
    plans = GreedyPlanner().plan(request(2500), [catalog])
    assert [p.variant for p in plans] == ["economy", "balanced", "premium"]
    for p in plans:
        assert p.total_price <= 2500
        assert (
            len({d.activity.id for d in p.days_plan}) == p.days
        )  # one distinct activity per day (no travel days here)
        assert validate(draft_from_plan(p, "FCO"), FakeInventory(catalog)) == []
    economy, balanced, premium = plans
    assert economy.total_price <= balanced.total_price <= premium.total_price
    assert premium.quality >= balanced.quality >= economy.quality


def test_economy_is_the_cheapest_feasible_trip():
    catalog = make_catalog()
    economy = GreedyPlanner().plan(request(2500), [catalog])[0]
    assert economy.days == 4 and economy.hotel.id == "h2"


def test_tight_budget_and_infeasibility():
    catalog = make_catalog()
    cheapest = minimum_cost(request(10**6), catalog)
    plans = GreedyPlanner().plan(request(cheapest), [catalog])
    assert plans and all(p.total_price <= cheapest for p in plans)
    assert GreedyPlanner().plan(request(cheapest - 1), [catalog]) == []


def test_not_enough_spots_makes_activities_unavailable():
    catalog = make_catalog(activity_spots=1)
    assert GreedyPlanner().plan(request(5000, travelers=2), [catalog]) == []


def test_validator_catches_tampering_and_inventory_changes():
    catalog = make_catalog()
    plan = GreedyPlanner().plan(request(2500), [catalog])[0]
    draft = draft_from_plan(plan, "FCO")
    inventory = FakeInventory(catalog)

    cheaper = draft.items[0].__class__(**{**draft.items[0].__dict__, "unit_price": 1})
    tampered = draft.__class__(**{**draft.__dict__, "items": (cheaper, *draft.items[1:])})
    assert any("price changed" in e for e in validate(tampered, inventory))

    over_budget = draft.__class__(**{**draft.__dict__, "budget": draft.total_price - 1})
    assert any("exceeds budget" in e for e in validate(over_budget, inventory))

    missing_night = draft.__class__(
        **{**draft.__dict__, "items": tuple(i for i in draft.items if i.kind != "hotel_night")[:]}
    )
    assert any("hotel nights" in e for e in validate(missing_night, inventory))

    inventory.hotels[plan.hotel.id].nightly[plan.start_date] = (60, 0)  # sold out meanwhile
    assert any("not enough rooms" in e for e in validate(draft, inventory))


def test_unlimited_budget_keeps_three_distinct_variants():
    """ADR-0022: without a budget, price is weighed against the quality-only trip, so the balanced variant
    sits between the cheapest and the best one instead of collapsing onto the economy one."""
    plans = {p.variant: p for p in GreedyPlanner().plan(request(None), [make_catalog()])}  # type: ignore[arg-type]
    assert set(plans) == {"economy", "balanced", "premium"}
    assert plans["economy"].total_price < plans["balanced"].total_price < plans["premium"].total_price
    assert all(p.budget is None for p in plans.values())


def test_anywhere_puts_each_variant_in_a_different_country():
    from dataclasses import replace

    spain = make_catalog()
    italy = replace(make_catalog(), code="IT", name="Italia", destination="Sicilia")
    req = replace(request(3000), distinct_countries=True)
    plans = GreedyPlanner().plan(req, [spain, italy])
    assert len({p.country_code for p in plans}) == 2  # two countries available: no third one to use
    same = GreedyPlanner().plan(request(3000), [spain, italy])
    assert len({p.country_code for p in same}) == 1  # without "ovunque" the best one wins every variant


def test_flights_that_leave_no_time_make_travel_days():
    """ADR-0023: landing late or leaving early leaves no time for an activity, so the planner prefers
    flights that do; when there are none, that day is a travel day instead of an impossible activity."""
    from dataclasses import replace

    from app.domain.schedule import arrival_window, departure_window

    base = make_catalog()
    late = {d: [replace(f, arrival_time="23:30") for f in fs] for d, fs in base.flights_out.items()}
    early = {d: [replace(f, departure_time="06:35") for f in fs] for d, fs in base.flights_back.items()}
    catalog = replace(base, flights_out=late, flights_back=early)
    plans = GreedyPlanner().plan(request(2500), [catalog])
    assert plans
    for p in plans:
        assert p.days_plan[0].activity is None and p.days_plan[-1].activity is None
        assert all(d.activity is not None for d in p.days_plan[1:-1])
        assert validate(draft_from_plan(p, "FCO"), FakeInventory(catalog)) == []
    assert arrival_window("23:30") == 0 and departure_window("06:35") == 0


def test_the_planner_prefers_a_flight_that_leaves_time_for_an_activity():
    from dataclasses import replace

    base = make_catalog()
    out = {
        d: [replace(f, id=f"{f.id}-late", arrival_time="23:30", price=f.price - 20), f]
        for d, fs in base.flights_out.items()
        for f in fs
    }
    catalog = replace(base, flights_out=out)
    plan = GreedyPlanner().plan(request(2500), [catalog])[0]
    assert plan.outbound.arrival_time == "10:00" and plan.days_plan[0].activity is not None


def test_the_validator_rejects_an_activity_that_does_not_fit_around_the_flights():
    from dataclasses import replace

    catalog = make_catalog()
    plan = GreedyPlanner().plan(request(2500), [catalog])[0]
    late = replace(plan.outbound, arrival_time="23:30")
    bad = replace(plan, outbound=late)
    inventory = FakeInventory(catalog)
    inventory.flights[late.id] = late
    assert any("does not fit around the flights" in e for e in validate(draft_from_plan(bad, "FCO"), inventory))


def _small_catalog(days_to_activities: dict[int, list[str]], out_flights, back_flights, prices=None) -> CountryCatalog:
    """Activities named by letter, available only on the given trip days (1-based from START)."""
    prices = prices or {}
    names = sorted({a for acts in days_to_activities.values() for a in acts})
    activities = [
        ActivityOption(
            n,
            n,
            "cultura",
            "",
            2,
            prices.get(n, 0),
            {START + timedelta(days=d - 1): 10 for d, acts in days_to_activities.items() if n in acts},
        )
        for n in names
    ]
    hotels = [HotelOption("h", "Hotel", 3, "Centro", {d: (50, 5) for d in DAYS})]
    return CountryCatalog("ES", "Spagna", "Barcellona", out_flights, back_flights, hotels, activities)


def test_unlimited_budget_keeps_the_guard_for_days_with_a_single_option_left():
    """Review finding: with no budget the 'last unused option of a pending day' guard was only a cost
    penalty, so a day could take another day's only option and the request came back infeasible."""
    out = {START: [FlightOption("o", "AB1", "AB", "FCO", "BCN", START, "08:00", "10:00", 50, 9)]}
    end = START + timedelta(days=3)
    back = {end: [FlightOption("b", "AB2", "AB", "BCN", "FCO", end, "18:00", "20:00", 50, 9)]}
    catalog = _small_catalog({1: ["A", "W"], 2: ["B", "W"], 3: ["C", "W"], 4: ["A", "B", "C"]}, out, back)
    scores = {"A": 0.9, "B": 0.9, "C": 0.9, "W": 0.1}
    for budget in (100000, None):
        req = PlanningRequest(budget, 2, [START], 4, 4, scores)
        assert GreedyPlanner().plan(req, [catalog]), budget


def test_a_compatible_flight_over_budget_falls_back_to_a_declared_travel_day():
    """Review finding: the compatible flight was always taken, even when only the cheaper late one fits."""
    end = START + timedelta(days=2)
    out = {
        START: [
            FlightOption("early", "AB1", "AB", "FCO", "BCN", START, "05:00", "07:00", 300, 9),
            FlightOption("late", "AB3", "AB", "FCO", "BCN", START, "21:00", "23:30", 50, 9),
        ]
    }
    back = {end: [FlightOption("b", "AB2", "AB", "BCN", "FCO", end, "18:00", "20:00", 50, 9)]}
    catalog = _small_catalog({1: ["A"], 2: ["B"], 3: ["C"]}, out, back)
    plans = GreedyPlanner().plan(PlanningRequest(400, 1, [START], 3, 3, {}), [catalog])
    assert plans and plans[0].outbound.id == "late" and plans[0].days_plan[0].activity is None
    assert minimum_cost(PlanningRequest(400, 1, [START], 3, 3, {}), catalog) == 200  # 50+50 flights + 2x50 hotel
