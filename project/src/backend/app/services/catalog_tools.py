"""Read-only catalog tools, available in every phase (ADR-0026).

"Quali destinazioni ci sono?", "che hotel avete ad Atene?", "ci sono voli da Napoli per l'Islanda a
febbraio?": the LLM understands the question and asks the code for the data it needs; the code reads the
database and returns only that. The tools never change requirements, phase or inventory, and the reply
goes through the same checks as every other one (ADR-0025).

Arguments are primitives validated here; countries and airports are the catalog's natural keys.
"""

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select

from app.catalog import resolve_month
from app.domain.planner import rooms_for
from app.domain.requirements import CATEGORIES, MONTHS_IT
from app.llm.base import ToolCall, ToolSpec
from app.models import Activity, Airport, Conversation, Country, Flight, Hotel, HotelAvailability
from app.textfmt import eur

if TYPE_CHECKING:
    from app.services.conversation import ConversationService
    from app.services.proposal_tools import ToolOutcome

log = logging.getLogger(__name__)

COUNTRY_HELP = "Paese: nome (es. Islanda) o codice ISO a 2 lettere"


class NoArgs(BaseModel):
    pass


class HotelsArgs(BaseModel):
    country: str = Field(description=COUNTRY_HELP)
    min_stars: int | None = Field(default=None, ge=1, le=5, description="Stelle minime, se l'utente le indica")
    month: int | None = Field(default=None, ge=1, le=12, description="Mese 1-12; vuoto = quello del viaggio, se noto")


class CatalogActivitiesArgs(BaseModel):
    query: str = Field(description="Cosa cerca l'utente, con le sue parole")
    country: str | None = Field(default=None, description=COUNTRY_HELP + "; vuoto per tutti i paesi")
    month: int | None = Field(default=None, ge=1, le=12, description="Mese 1-12, se l'utente lo indica")


class AvailabilityArgs(BaseModel):
    country: str = Field(description=COUNTRY_HELP)
    month: int = Field(ge=1, le=12, description="Mese 1-12")
    departure_airport: str | None = Field(default=None, description="FCO, MXP o NAP; vuoto per tutti e tre")
    travelers: int | None = Field(default=None, ge=1, le=9, description="Numero di viaggiatori, se noto")


SPECS = [
    ToolSpec("list_destinations", "Elenca le destinazioni del catalogo, con la loro descrizione.", NoArgs),
    ToolSpec("list_departure_airports", "Elenca gli aeroporti da cui si può partire.", NoArgs),
    ToolSpec("get_hotels", "Elenca gli hotel di un paese con stelle, zona e prezzo per notte.", HotelsArgs),
    ToolSpec(
        "search_activities",
        "Cerca attività nel catalogo (anche per nome), con categoria, pubblico, prezzo e mesi.",
        CatalogActivitiesArgs,
    ),
    ToolSpec(
        "check_availability",
        "Disponibilità reale in un mese: giorni con voli con posti e hotel con camere, prezzi minimi.",
        AvailabilityArgs,
    ),
]
NAMES = {s.name for s in SPECS}


class CatalogToolbox:
    def __init__(self, service: "ConversationService", conv: Conversation):
        self.service = service
        self.session = service.session
        self.conv = conv

    def execute(self, call: ToolCall) -> "ToolOutcome":
        from app.services.proposal_tools import ToolOutcome

        spec = next((s for s in SPECS if s.name == call.name), None)
        if spec is None:
            return ToolOutcome(content={"errore": f"Strumento sconosciuto: {call.name}."}, summary="")
        try:
            args = spec.parameters.model_validate(call.arguments)
        except ValidationError as exc:
            return ToolOutcome(content={"errore": f"Argomenti non validi: {exc.errors()[0]['msg']}."}, summary="")
        with self.service.tracer.observation(f"tool.{call.name}", as_type="tool", input=args.model_dump()) as span:
            content, summary = getattr(self, f"_{call.name}")(args)
            span.update(output=content, level="WARNING" if "errore" in content else "DEFAULT")
        log.info("tool.called", extra={"tool": call.name, "ok": "errore" not in content, "terminal": False})
        return ToolOutcome(content=content, summary=summary)

    # --- Tools: each returns (content for the LLM, summary written by code) ----------------

    def _list_destinations(self, args: NoArgs) -> tuple[dict, str]:
        countries = self.session.scalars(select(Country).order_by(Country.name)).all()
        counts = dict(
            self.session.execute(select(Activity.country_code, func.count()).group_by(Activity.country_code)).all()
        )
        rows = [
            {
                "paese": c.name,  # the tools also accept the name: no code for the model to echo
                "zona": c.destination,
                "descrizione": c.description,
                "attività_in_catalogo": counts.get(c.code, 0),
            }
            for c in countries
        ]
        names = ", ".join(f"{c.name} ({c.destination})" for c in countries)
        return {"destinazioni": rows}, f"Le destinazioni del catalogo sono: {names}."

    def _list_departure_airports(self, args: NoArgs) -> tuple[dict, str]:
        airports = self.session.scalars(select(Airport).where(Airport.kind == "departure").order_by(Airport.city)).all()
        names = ", ".join(f"{a.city} {a.name} ({a.code})" for a in airports)
        rows = [{"codice": a.code, "città": a.city, "aeroporto": a.name} for a in airports]
        return {"aeroporti_di_partenza": rows}, f"Si può partire da {names}."

    def _get_hotels(self, args: HotelsArgs) -> tuple[dict, str]:
        country = self._country(args.country)
        if country is None:
            return self._unknown_country(args.country)
        hotels = self.session.scalars(
            select(Hotel).where(Hotel.country_code == country.code).order_by(Hotel.stars, Hotel.name)
        ).all()
        if args.min_stars:
            hotels = [h for h in hotels if h.stars >= args.min_stars]
        # Prices of the requested month (or the trip's): a minimum over the whole year would mislead.
        month = args.month or self.service._requirements(self.conv).month
        days = resolve_month(self.session, month, self.service.today) if month else []
        query = (
            select(HotelAvailability.hotel_id, func.min(HotelAvailability.price), func.max(HotelAvailability.price))
            .where(HotelAvailability.hotel_id.in_([h.id for h in hotels]), HotelAvailability.rooms_left > 0)
            .group_by(HotelAvailability.hotel_id)
        )
        if days:
            query = query.where(HotelAvailability.date.between(days[0], days[-1]))
        prices = {hid: (lo, hi) for hid, lo, hi in self.session.execute(query).all()}
        rows = [
            {
                "hotel": h.name,
                "stelle": h.stars,
                "zona": h.neighborhood,
                "descrizione": h.description,
                "prezzo_camera_notte_da": prices.get(h.id, (None, None))[0],
                "prezzo_camera_notte_a": prices.get(h.id, (None, None))[1],
            }
            for h in hotels
        ]
        if not rows:
            return {
                "hotel": [],
                "nota": "nessun hotel con queste stelle",
            }, f"A {country.destination} non ci sono hotel così."
        cheapest = min((r["prezzo_camera_notte_da"] for r in rows if r["prezzo_camera_notte_da"]), default=None)
        stars = f"da {rows[0]['stelle']}★ a {rows[-1]['stelle']}★"
        price = f", da {eur(cheapest)} a notte per camera" if cheapest else ""
        return {
            "paese": country.name,
            "periodo_prezzi": f"{MONTHS_IT[month - 1]} {days[0].year}" if days else "tutto il catalogo",
            "nota_prezzi": "prezzo per camera (2 persone) a notte",
            "hotel": rows,
        }, f"A {country.destination} ci sono {len(rows)} hotel, {stars}{price}."

    def _search_activities(self, args: CatalogActivitiesArgs) -> tuple[dict, str]:
        from app.rag.retriever import audience_of, with_audience
        from app.services.proposal_tools import named

        codes = [args.country.upper()] if args.country else list(self.session.scalars(select(Country.code)))
        if args.country and self._country(args.country) is None:
            return self._unknown_country(args.country)
        activities = list(self.session.scalars(select(Activity).where(Activity.country_code.in_(codes))))
        if args.month:
            activities = [a for a in activities if args.month in a.months]
        index = self.service.index_factory(activities)
        months = [args.month] if args.month else list(range(1, 13))
        relevance: dict[str, float] = {}
        for month in months:  # without a month, the best match in any month
            for aid, score in index.similarities(args.query, codes, month).items():
                relevance[aid] = max(relevance.get(aid, 0.0), score)
        relevance = with_audience(relevance, activities, audience_of(self.service._requirements(self.conv)))
        ranked = sorted(activities, key=lambda a: (-named(args.query, a.name), -relevance.get(a.id, 0.0)))[:5]
        country_names = dict(self.session.execute(select(Country.code, Country.name)).all())
        rows = [
            {
                "attività": a.name,
                "paese": country_names.get(a.country_code),
                "categoria": CATEGORIES.get(a.category, a.category),
                "pubblico": a.targets,
                "prezzo_a_persona": a.price,
                "durata_ore": a.duration_hours,
                "mesi": [MONTHS_IT[m - 1] for m in sorted(a.months)],
                "descrizione": a.description,
            }
            for a in ranked
        ]
        names = ", ".join(r["attività"] for r in rows[:3])
        return {"risultati": rows}, f"Tra le attività più vicine a quello che cerchi: {names}."

    def _check_availability(self, args: AvailabilityArgs) -> tuple[dict, str]:
        country = self._country(args.country)
        if country is None:
            return self._unknown_country(args.country)
        days = resolve_month(self.session, args.month, self.service.today)
        month_name = MONTHS_IT[args.month - 1]
        if not days:
            return {"errore": f"{month_name} non è coperto dal catalogo"}, f"Il catalogo non copre {month_name}."
        travelers = args.travelers or 1
        rooms = rooms_for(travelers)
        airports = (
            [args.departure_airport.upper()]
            if args.departure_airport
            else list(self.session.scalars(select(Airport.code).where(Airport.kind == "departure")))
        )
        first, last = days[0], days[-1]
        airport_names = {a.code: f"{a.city} {a.name}" for a in self.session.scalars(select(Airport))}
        flights = []
        for code in airports:
            out = self._flights(code, country.airport_code, first, last, travelers)
            back = self._flights(country.airport_code, code, first, last, travelers)
            flights.append(
                {
                    "partenza": code,
                    "aeroporto": airport_names.get(code, code),
                    "giorni_con_voli_andata": out[0],
                    "prezzo_minimo_andata_a_persona": out[1],
                    "giorni_con_voli_ritorno": back[0],
                    "prezzo_minimo_ritorno_a_persona": back[1],
                }
            )
        nights = self.session.execute(
            select(func.count(func.distinct(HotelAvailability.date)), func.min(HotelAvailability.price))
            .join(Hotel, Hotel.id == HotelAvailability.hotel_id)
            .where(
                Hotel.country_code == country.code,
                HotelAvailability.date.between(first, last),
                HotelAvailability.rooms_left >= rooms,
            )
        ).one()
        activities = self.session.scalar(
            select(func.count()).select_from(Activity).where(Activity.country_code == country.code)
        )
        in_month = sum(
            1
            for a in self.session.scalars(select(Activity).where(Activity.country_code == country.code))
            if args.month in a.months
        )
        content = {
            "paese": country.name,
            "zona": country.destination,
            "mese": month_name,
            "anno": first.year,  # "ottobre" may be next year's October: say it (catalog window)
            "giorni_del_mese_nel_catalogo": len(days),
            "viaggiatori": travelers,
            "voli": flights,
            "notti_con_hotel_disponibili": nights[0],
            "prezzo_minimo_camera_notte": nights[1],
            "attività_nel_mese": f"{in_month} su {activities}",
        }
        best = [f for f in flights if f["giorni_con_voli_andata"]]
        if not best:
            summary = f"A {month_name} {first.year} non ci sono voli con posti per {country.name}."
        else:
            cheapest = min(best, key=lambda f: f["prezzo_minimo_andata_a_persona"])
            summary = (
                f"A {month_name} {first.year} per {country.destination} ci sono voli di andata in "
                f"{cheapest['giorni_con_voli_andata']} giorni da {cheapest['aeroporto']}, da "
                f"{eur(cheapest['prezzo_minimo_andata_a_persona'])} a persona, "
                f"e hotel disponibili in {nights[0]} notti."
            )
        return content, summary

    # --- Helpers ---------------------------------------------------------------------------

    def _country(self, code: str) -> Country | None:
        value = code.strip()
        country = self.session.get(Country, value.upper()) if len(value) == 2 else None
        if country is None:  # the model may pass the name
            country = self.session.scalar(select(Country).where(func.lower(Country.name) == value.lower()))
        return country

    def _unknown_country(self, value: str) -> tuple[dict, str]:
        names = ", ".join(self.session.scalars(select(Country.name).order_by(Country.name)))
        return (
            {"errore": f"'{value}' non è nel catalogo", "destinazioni_disponibili": names},
            f"Al momento non abbiamo offerte per quella destinazione: le mete sono {names}.",
        )

    def _flights(self, origin: str, destination: str, first, last, travelers: int) -> tuple[int, int | None]:
        days, price = self.session.execute(
            select(func.count(func.distinct(Flight.date)), func.min(Flight.price)).where(
                Flight.origin == origin,
                Flight.destination == destination,
                Flight.date.between(first, last),
                Flight.seats_left >= travelers,
            )
        ).one()
        return days, price
