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
        return FlightFacts(f.origin, f.destination, f.date, f.price, f.seats_left) if f else None

    def hotel_night(self, hotel_id, night):
        return self.hotels[hotel_id].nightly.get(night)

    def activity(self, activity_id, day):
        a = self.activities[activity_id]
        return (a.price, a.availability[day]) if day in a.availability else None


def test_three_variants_within_budget_and_valid():
    catalog = make_catalog()
    plans = GreedyPlanner().plan(request(2500), [catalog])
    assert [p.variant for p in plans] == ["economy", "balanced", "premium"]
    for p in plans:
        assert p.total_price <= 2500
        assert len({d.activity.id for d in p.days_plan}) == p.days  # one distinct activity per day
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
