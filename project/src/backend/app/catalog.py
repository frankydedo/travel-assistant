"""Catalog access: planner snapshots, inventory reads for the validator, month resolution."""

import calendar
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.planner import ActivityOption, CountryCatalog, FlightOption, HotelOption
from app.domain.requirements import CatalogFacts
from app.domain.validator import FlightFacts
from app.models import (
    Activity,
    ActivityAvailability,
    Airport,
    CatalogMeta,
    Country,
    Flight,
    Hotel,
    HotelAvailability,
)


def catalog_window(session: Session) -> tuple[date, date]:
    meta = session.scalar(select(CatalogMeta))
    if meta is None:
        raise RuntimeError("catalog not seeded")
    return meta.start_date, meta.end_date


def resolve_month(session: Session, month: int, today: date | None = None) -> list[date]:
    """Start dates for a trip in ``month``: the month's next occurrence inside the catalog window,
    from tomorrow onwards. Assumption (README): the trip starts in the month and may end after it."""
    today = today or date.today()
    start, end = catalog_window(session)
    earliest = max(start, today + timedelta(days=1))
    for year in (earliest.year, earliest.year + 1):
        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
        days = [d for d in days if earliest <= d <= end]
        if days:
            return days
    return []


def catalog_facts(session: Session, max_days: int) -> CatalogFacts:
    countries = set(session.scalars(select(Country.code)))
    departures = set(session.scalars(select(Airport.code).where(Airport.kind == "departure")))
    return CatalogFacts(country_codes=countries, departure_airports=departures, max_days=max_days)


def load_catalogs(
    session: Session, country_codes: list[str], departure_airport: str, date_from: date, date_to: date
) -> list[CountryCatalog]:
    countries = session.scalars(select(Country).where(Country.code.in_(country_codes))).all()
    by_airport = {c.airport_code: c for c in countries}
    out: dict[str, dict[date, list[FlightOption]]] = defaultdict(lambda: defaultdict(list))
    back: dict[str, dict[date, list[FlightOption]]] = defaultdict(lambda: defaultdict(list))
    flights = session.scalars(
        select(Flight).where(
            Flight.date.between(date_from, date_to),
            (
                (Flight.origin == departure_airport) & Flight.destination.in_(by_airport)
                | Flight.origin.in_(by_airport) & (Flight.destination == departure_airport)
            ),
        )
    )
    for f in flights:
        option = _flight_option(f)
        if f.origin == departure_airport:
            out[by_airport[f.destination].code][f.date].append(option)
        else:
            back[by_airport[f.origin].code][f.date].append(option)

    hotels_by_country: dict[str, dict[str, Hotel]] = defaultdict(dict)
    for h in session.scalars(select(Hotel).where(Hotel.country_code.in_(country_codes))):
        hotels_by_country[h.country_code][h.id] = h
    nightly: dict[str, dict[date, tuple[int, int]]] = defaultdict(dict)
    hotel_ids = [hid for hs in hotels_by_country.values() for hid in hs]
    for row in session.scalars(
        select(HotelAvailability).where(
            HotelAvailability.hotel_id.in_(hotel_ids), HotelAvailability.date.between(date_from, date_to)
        )
    ):
        nightly[row.hotel_id][row.date] = (row.price, row.rooms_left)

    activities_by_country: dict[str, dict[str, Activity]] = defaultdict(dict)
    for a in session.scalars(select(Activity).where(Activity.country_code.in_(country_codes))):
        activities_by_country[a.country_code][a.id] = a
    spots: dict[str, dict[date, int]] = defaultdict(dict)
    activity_ids = [aid for acts in activities_by_country.values() for aid in acts]
    for row in session.scalars(
        select(ActivityAvailability).where(
            ActivityAvailability.activity_id.in_(activity_ids),
            ActivityAvailability.date.between(date_from, date_to),
        )
    ):
        spots[row.activity_id][row.date] = row.spots_left

    catalogs = []
    for c in countries:
        catalogs.append(
            CountryCatalog(
                code=c.code,
                name=c.name,
                destination=c.destination,
                flights_out=dict(out[c.code]),
                flights_back=dict(back[c.code]),
                hotels=[
                    HotelOption(h.id, h.name, h.stars, h.neighborhood, nightly.get(h.id, {}))
                    for h in hotels_by_country[c.code].values()
                ],
                activities=[
                    ActivityOption(
                        a.id,
                        a.name,
                        a.category,
                        a.description,
                        a.duration_hours,
                        a.price,
                        spots.get(a.id, {}),
                        a.description_ai_generated,
                    )
                    for a in activities_by_country[c.code].values()
                ],
            )
        )
    return sorted(catalogs, key=lambda c: c.code)


def _flight_option(f: Flight) -> FlightOption:
    return FlightOption(
        f.id,
        f.flight_number,
        f.carrier,
        f.origin,
        f.destination,
        f.date,
        f.departure_time,
        f.arrival_time,
        f.price,
        f.seats_left,
    )


class SqlInventory:
    """``InventoryReader`` over the database: always reads fresh rows."""

    def __init__(self, session: Session):
        self.session = session

    def destination_airport(self, country_code: str) -> str | None:
        country = self.session.get(Country, country_code)
        return country.airport_code if country else None

    def flight(self, flight_id: str) -> FlightFacts | None:
        f = self.session.get(Flight, flight_id)
        if f is None:
            return None
        return FlightFacts(f.origin, f.destination, f.date, f.price, f.seats_left, f.departure_time, f.arrival_time)

    def hotel_night(self, hotel_id: str, night: date) -> tuple[int, int] | None:
        row = self.session.get(HotelAvailability, (hotel_id, night))
        return (row.price, row.rooms_left) if row else None

    def activity(self, activity_id: str, day: date) -> tuple[int, int] | None:
        act = self.session.get(Activity, activity_id)
        row = self.session.get(ActivityAvailability, (activity_id, day))
        return (act.price, row.spots_left) if act and row else None

    def activity_duration(self, activity_id: str) -> int | None:
        act = self.session.get(Activity, activity_id)
        return act.duration_hours if act else None
