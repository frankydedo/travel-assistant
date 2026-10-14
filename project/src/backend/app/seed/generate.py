"""Deterministic synthetic catalog (ADR-0013).

Same seed + same seed month => identical data. The calendar is relative to the month the seed runs
in (the 12 months after it), so the data never "expires". Text (descriptions, targets) comes from the
versioned JSON fixtures; numbers (prices, availability) are generated here.
"""

import calendar
import json
import random
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from app.models import (
    Activity,
    ActivityAvailability,
    Airport,
    CatalogMeta,
    Country,
    Flight,
    Hotel,
    HotelAvailability,
    catalog_id,
)

FIXTURES = Path(__file__).parent / "fixtures"
DEFAULT_SEED = 42

# Fictional carriers: no real airline brands.
CARRIERS = [("AB", "Airone Blu"), ("AS", "Ali del Sud"), ("PA", "Polare Air")]
LONG_HAUL_CARRIER = ("SW", "Sakura Wings")
DEPARTURE_PRICE_FACTOR = {"FCO": 1.0, "MXP": 1.05, "NAP": 1.1}  # NAP has fewer routes: slightly pricier


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def catalog_window(today: date) -> tuple[date, date]:
    """The 12 months following the current one."""
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    start = date(year, month, 1)
    end_year, end_month = (year + 1, month - 1) if month > 1 else (year, 12)
    end = date(end_year, end_month, calendar.monthrange(end_year, end_month)[1])
    return start, end


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _weekday_flight_factor(d: date) -> float:
    return {4: 1.15, 6: 1.15, 1: 0.9, 2: 0.9}.get(d.weekday(), 1.0)


def _fmt_time(minutes: int) -> str:
    day_offset, minutes = divmod(minutes, 24 * 60)
    text = f"{minutes // 60:02d}:{minutes % 60:02d}"
    return text + (f"+{day_offset}" if day_offset else "")


def generate(session: Session, today: date | None = None, seed: int = DEFAULT_SEED) -> dict[str, int]:
    rng = random.Random(seed)
    today = today or date.today()
    start, end = catalog_window(today)
    days = _days(start, end)

    data = load_fixture("countries.json")
    hotels = load_fixture("hotels.json")
    activities = load_fixture("activities.json")
    countries = {c["code"]: c for c in data["countries"]}

    for model in (ActivityAvailability, HotelAvailability, Flight, Activity, Hotel, Airport, Country, CatalogMeta):
        session.execute(delete(model))

    session.add(CatalogMeta(id=catalog_id("catalog", "meta"), start_date=start, end_date=end, seed=seed))
    for a in data["departure_airports"]:
        session.add(Airport(code=a["code"], city=a["city"], name=a["name"], kind="departure"))
    for c in data["countries"]:
        session.add(
            Country(
                code=c["code"],
                name=c["name"],
                destination=c["destination"],
                airport_code=c["airport"]["code"],
                description=c["description"],
            )
        )
        session.add(
            Airport(
                code=c["airport"]["code"],
                city=c["airport"]["city"],
                name=c["airport"]["name"],
                kind="destination",
                country_code=c["code"],
            )
        )

    # Flights: every day, both directions, for every (departure, destination) pair.
    flights: list[dict] = []
    number = 100
    for dep in data["departure_airports"]:
        for c in data["countries"]:
            long_haul = c["flight_hours"] > 8
            minutes = round(c["flight_hours"] * 60)
            per_day = 1 if long_haul else 2
            for direction in ("out", "back"):
                origin, destination = (
                    (dep["code"], c["airport"]["code"]) if direction == "out" else (c["airport"]["code"], dep["code"])
                )
                carrier_code, carrier = LONG_HAUL_CARRIER if long_haul else rng.choice(CARRIERS)
                numbers = [number + i for i in range(per_day)]
                number += per_day
                slots = [rng.randrange(6 * 60, 11 * 60, 5), rng.randrange(14 * 60, 20 * 60, 5)][:per_day]
                for d in days:
                    base = c["flight_base_price"] * c["season_factors"][d.month - 1] * _weekday_flight_factor(d)
                    base *= DEPARTURE_PRICE_FACTOR[dep["code"]]
                    sold_out_day = rng.random() < 0.03  # whole route sold out on some days (edge case)
                    for slot, flight_no in zip(slots, numbers, strict=True):
                        flights.append(
                            {
                                "id": catalog_id("flight", f"{carrier_code}{flight_no}:{d.isoformat()}"),
                                "flight_number": f"{carrier_code}{flight_no}",
                                "carrier": carrier,
                                "origin": origin,
                                "destination": destination,
                                "date": d,
                                "departure_time": _fmt_time(slot),
                                "arrival_time": _fmt_time(slot + minutes),
                                "price": round(base * rng.uniform(0.85, 1.2)),
                                "seats_left": 0 if sold_out_day or rng.random() < 0.05 else rng.randint(2, 60),
                            }
                        )
    session.execute(insert(Flight), flights)

    # Hotels: price per room per night, seasonal and weekend factors.
    hotel_rows: list[dict] = []
    for h in hotels:
        hotel_id = catalog_id("hotel", h["id"])
        session.add(
            Hotel(
                id=hotel_id,
                slug=h["id"],
                country_code=h["country_code"],
                name=h["name"],
                stars=h["stars"],
                neighborhood=h["neighborhood"],
                description=h["description"],
                base_price=h["base_price_per_room"],
            )
        )
        factors = countries[h["country_code"]]["season_factors"]
        for d in days:
            weekend = 1.2 if d.weekday() in (4, 5) else 1.0
            price = round(h["base_price_per_room"] * factors[d.month - 1] * weekend * rng.uniform(0.95, 1.1))
            rooms_left = 0 if rng.random() < 0.06 else rng.randint(1, 10)
            hotel_rows.append({"hotel_id": hotel_id, "date": d, "price": price, "rooms_left": rooms_left})
    session.flush()
    session.execute(insert(HotelAvailability), hotel_rows)

    # Activities: available only in their months and not on closed weekdays.
    activity_rows: list[dict] = []
    for a in activities:
        activity_id = catalog_id("activity", a["id"])
        session.add(
            Activity(
                id=activity_id,
                slug=a["id"],
                country_code=a["country_code"],
                name=a["name"],
                category=a["category"],
                targets=a["targets"],
                description=a["description"],
                # Fixture texts were written with AI and reviewed (ADR-0013): flagged unless stated otherwise.
                description_ai_generated=a.get("description_ai_generated", True),
                price=a["price_per_person"],
                duration_hours=a["duration_hours"],
                months=a["months"],
                closed_weekdays=a.get("closed_weekdays", []),
            )
        )
        for d in days:
            if d.month not in a["months"] or d.weekday() in a.get("closed_weekdays", []):
                continue
            spots = 0 if rng.random() < 0.04 else rng.randint(4, 30)
            activity_rows.append({"activity_id": activity_id, "date": d, "spots_left": spots})
    session.flush()
    session.execute(insert(ActivityAvailability), activity_rows)
    session.commit()
    return {
        "flights": len(flights),
        "hotel_nights": len(hotel_rows),
        "activity_days": len(activity_rows),
        "hotels": len(hotels),
        "activities": len(activities),
    }
