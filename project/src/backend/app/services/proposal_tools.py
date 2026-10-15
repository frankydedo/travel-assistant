"""Tools available to the LLM in the proposal phase (ADR-0001: tool calling only inside a phase).

Design rules:
- The LLM never sees or passes ids: it refers to "variant + day", and the code resolves the reference.
- Arguments are plain strings, integers and enums (no optional or nested schemas), because providers
  support different subsets of JSON Schema for tools.
- Every call is validated and executed by code. Changes go through catalog, RAG and validator and create
  a *new* validated itinerary; an existing proposal is never edited in place.
- Tools that change the phase (select, update requirements, out of scope) are terminal: control goes back
  to the orchestrator. The others (modify, look up) feed their result back to the LLM.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from app.catalog import SqlInventory, load_catalogs
from app.domain.modify import ModificationError, rehydrate, replace_activity, replace_hotel
from app.domain.phases import Phase, change_phase
from app.domain.requirements import CATEGORIES, mentions_exact_date
from app.domain.validator import draft_from_plan, validate
from app.llm.base import ToolCall, ToolSpec
from app.llm.mock import VARIANT_LABELS
from app.models import Activity, Conversation, Country, Itinerary
from app.rag.retriever import audience_of, with_audience
from app.services.catalog_tools import NAMES as CATALOG_NAMES
from app.services.catalog_tools import SPECS as CATALOG_SPECS
from app.textfmt import budget_value, eur, of_budget

if TYPE_CHECKING:
    from app.services.conversation import ConversationService

log = logging.getLogger(__name__)

Variant = Literal["economy", "balanced", "premium"]


class SelectVariantArgs(BaseModel):
    variant: Variant = Field(description="La variante scelta dall'utente")


class UpdateRequirementsArgs(BaseModel):
    change: str = Field(description="La modifica ai requisiti chiesta dall'utente, con le sue parole")


class SwapActivityArgs(BaseModel):
    variant: Variant
    day: int = Field(ge=1, le=14, description="Numero del giorno del viaggio (1 = primo giorno)")
    request: str = Field(description="Che tipo di attività vuole l'utente al posto di quella attuale")
    category: Literal["cultura", "sport", "relax", "nightlife", "natura", "gastronomia", "qualsiasi"] = Field(
        description="Categoria richiesta dall'utente; 'qualsiasi' se non ne indica una"
    )


class ChangeHotelArgs(BaseModel):
    variant: Variant
    direction: Literal["better", "cheaper"] = Field(description="better = più stelle, cheaper = meno costoso")


class SearchActivitiesArgs(BaseModel):
    query: str = Field(description="Cosa cerca l'utente, in linguaggio naturale")


class ItineraryDetailsArgs(BaseModel):
    variant: Variant


class NoArgs(BaseModel):
    pass


SPECS = [
    ToolSpec("select_variant", "L'utente sceglie una delle varianti proposte.", SelectVariantArgs),
    ToolSpec(
        "update_requirements",
        "L'utente cambia un requisito del viaggio (budget, mese, durata, destinazione, partenza, viaggiatori, "
        "preferenze): serve una nuova pianificazione.",
        UpdateRequirementsArgs,
    ),
    ToolSpec("swap_activity", "Sostituisce l'attività di un giorno di una variante.", SwapActivityArgs),
    ToolSpec("change_hotel", "Cambia l'hotel di una variante con uno migliore o più economico.", ChangeHotelArgs),
    ToolSpec("search_activities", "Cerca attività del catalogo nella destinazione del viaggio.", SearchActivitiesArgs),
    ToolSpec("get_itinerary_details", "Restituisce i dettagli di una variante.", ItineraryDetailsArgs),
    ToolSpec("flag_out_of_scope", "Il messaggio non riguarda l'organizzazione del viaggio.", NoArgs),
]
# Read-only catalog tools are available here too (ADR-0026); search_activities stays the trip-focused one.
SPECS += [spec for spec in CATALOG_SPECS if spec.name != "search_activities"]
TERMINAL = {"select_variant", "update_requirements", "flag_out_of_scope"}


@dataclass
class ToolOutcome:
    content: dict  # what the LLM sees as the tool result
    summary: str  # Italian, written by code: used by the mock and as fallback reply
    terminal: bool = False
    itinerary_ids: list[str] = field(default_factory=list)


class ProposalToolbox:
    def __init__(self, service: "ConversationService", conv: Conversation):
        self.service = service
        self.session = service.session
        self.conv = conv

    # --- Context for the LLM (no ids) ---------------------------------------------------

    def active(self) -> dict[str, Itinerary]:
        return {it.variant: it for it in self.service._active_itineraries(self.conv)}

    def context(self) -> list[dict]:
        return [self._describe(it) for it in self.active().values()]

    @staticmethod
    def _describe(it: Itinerary, detailed: bool = False) -> dict:
        v = it.view
        return {
            "variant": it.variant,
            "nome_variante": VARIANT_LABELS[it.variant],
            "stato": "scelta" if it.status == "selected" else "proposta",
            "destinazione": v["destination"],
            "dal": v["start_date"],
            "al": v["end_date"],
            "giorni": v["days"],
            "viaggiatori": v["travelers"],
            "hotel": f"{v['hotel']['name']} ({v['hotel']['stars']}★)",
            "totale_euro": it.total_price,
            "budget_euro": budget_value(it.budget_total),
            "programma": [_program_day(d, detailed) for d in v["days_plan"]],
        }

    # --- Execution ---------------------------------------------------------------------

    def execute(self, call: ToolCall) -> ToolOutcome:
        if call.name in CATALOG_NAMES and call.name != "search_activities":
            from app.services.catalog_tools import CatalogToolbox

            return CatalogToolbox(self.service, self.conv).execute(call)
        spec = next((s for s in SPECS if s.name == call.name), None)
        if spec is None:
            return self._error(f"Strumento sconosciuto: {call.name}.", user_text="")
        try:
            args = spec.parameters.model_validate(call.arguments)
        except ValidationError as exc:
            return self._error(f"Argomenti non validi per {call.name}: {exc.errors()[0]['msg']}.", user_text="")
        with self.service.tracer.observation(f"tool.{call.name}", as_type="tool", input=args.model_dump()) as span:
            try:
                outcome = getattr(self, f"_{call.name}")(args)
            except ModificationError as exc:
                outcome = self._error(str(exc))
            span.update(output=outcome.content, level="WARNING" if "errore" in outcome.content else "DEFAULT")
        log.info(
            "tool.called",
            extra={"tool": call.name, "ok": "errore" not in outcome.content, "terminal": outcome.terminal},
        )
        return outcome

    @staticmethod
    def _error(message: str, user_text: str | None = None) -> ToolOutcome:
        """``message`` goes to the LLM; ``summary`` may reach the user, so it must read as a reply."""
        return ToolOutcome(content={"errore": message}, summary=message if user_text is None else user_text)

    def _itinerary(self, variant: str) -> Itinerary:
        it = self.active().get(variant)
        if it is None:
            raise ModificationError(f"La variante {VARIANT_LABELS.get(variant, variant)} non è tra quelle proposte.")
        return it

    # Terminal tools: the orchestrator writes the reply.

    def _select_variant(self, args: SelectVariantArgs) -> ToolOutcome:
        self.service.select(self.conv, self._itinerary(args.variant))
        return ToolOutcome(content={"ok": True}, summary="", terminal=True)

    def _update_requirements(self, args: UpdateRequirementsArgs) -> ToolOutcome:
        current = self.service._requirements(self.conv)
        extraction = self.service.interpreter.extract_requirements(
            args.change, current, self.service._history(self.conv)
        )
        update = extraction.value.requirements
        if update.is_empty() or current.merge(update) == current:  # nothing would change: no replanning
            if mentions_exact_date(args.change) or mentions_exact_date(self.service._last_user_text or ""):
                # Nothing to change: the orchestrator explains that dates are month-only (fixed text).
                return ToolOutcome(content={"ok": True}, summary="", terminal=True)
            return self._error(
                "Non ho capito quale requisito cambiare: chiedi all'utente di specificarlo.",
                user_text="Non ho capito cosa vuoi cambiare: dimmi quale requisito modificare (budget, mese, "
                "durata, partenza, numero di persone o interessi).",
            )
        self.service._apply_update(self.conv, current, update)
        return ToolOutcome(content={"ok": True}, summary="", terminal=True)

    def _flag_out_of_scope(self, args: NoArgs) -> ToolOutcome:
        self.service._refuse(self.conv)
        return ToolOutcome(content={"ok": True}, summary="", terminal=True)

    # Modifications: a new validated itinerary replaces the old one.

    def _swap_activity(self, args: SwapActivityArgs) -> ToolOutcome:
        old = self._itinerary(args.variant)
        catalog, plan = self._rehydrate(old)
        relevance = self._relevance(args.request, old)
        category = None if args.category == "qualsiasi" else args.category
        new_plan, before, after = replace_activity(plan, args.day, catalog, relevance, category)
        new = self._replace(old, new_plan)
        summary = (
            f"Nella variante {VARIANT_LABELS[old.variant]} ho sostituito «{before.name}» del giorno {args.day} "
            f"con «{after.name}»: il nuovo totale è {eur(new.total_price)}{of_budget(new.budget_total)}."
        )
        return ToolOutcome(
            content={
                "modifica_effettuata": True,
                "variante": VARIANT_LABELS[old.variant],
                "giorno": args.day,
                "attività_precedente": before.name,
                "nuova_attività": after.name,
                "categoria": CATEGORIES.get(after.category, after.category),
                "descrizione": after.description,
                "totale_precedente_euro": old.total_price,
                "nuovo_totale_euro": new.total_price,
                "budget_euro": budget_value(new.budget_total),
            },
            summary=summary,
            itinerary_ids=[new.id],
        )

    def _change_hotel(self, args: ChangeHotelArgs) -> ToolOutcome:
        old = self._itinerary(args.variant)
        catalog, plan = self._rehydrate(old)
        previous = f"{plan.hotel.name} ({plan.hotel.stars}★)"
        new_plan, hotel = replace_hotel(plan, args.direction, catalog)
        new = self._replace(old, new_plan)
        summary = (
            f"Nella variante {VARIANT_LABELS[old.variant]} ho sostituito {previous} con {hotel.name} "
            f"({hotel.stars}★): il nuovo totale è {eur(new.total_price)}{of_budget(new.budget_total)}."
        )
        return ToolOutcome(
            content={
                "modifica_effettuata": True,
                "variante": VARIANT_LABELS[old.variant],
                "hotel_precedente": previous,
                "nuovo_hotel": f"{hotel.name} ({hotel.stars}★)",
                "quartiere": hotel.neighborhood,
                "totale_precedente_euro": old.total_price,
                "nuovo_totale_euro": new.total_price,
                "budget_euro": budget_value(new.budget_total),
            },
            summary=summary,
            itinerary_ids=[new.id],
        )

    # Look-ups: read only.

    def _search_activities(self, args: SearchActivitiesArgs) -> ToolOutcome:
        active = list(self.active().values())
        if not active:
            return self._error("Non ci sono proposte attive.")
        # Every country of the active variants: with «ovunque» each variant can be in a different one.
        by_country = {it.country_code: it for it in sorted(active, key=lambda it: it.variant)}
        relevance: dict[str, float] = {}
        months: dict[str, set[int]] = {}
        for code, it in by_country.items():
            relevance.update(self._relevance(args.query, it))
            months[code] = {it.start_date.month, it.end_date.month}
        activities = self.session.scalars(select(Activity).where(Activity.country_code.in_(list(by_country))))
        # Hybrid ranking: an activity named in the question ("cosa si fa alle Terme Segestane?") comes first
        # even when the embedding misses it; semantic similarity orders the rest.
        ranked = sorted(activities, key=lambda a: (-named(args.query, a.name), -relevance.get(a.id, 0.0)))[:5]
        results = [
            {
                "attività": a.name,
                "categoria": CATEGORIES.get(a.category, a.category),
                "prezzo_a_persona": a.price,
                "disponibile_nel_periodo": bool(months[a.country_code] & set(a.months)),
                "descrizione": a.description,
            }
            for a in ranked
        ]
        names = ", ".join(r["attività"] for r in results[:3])
        return ToolOutcome(
            content={"risultati": results}, summary=f"Tra le attività più vicine a quello che cerchi: {names}."
        )

    def _get_itinerary_details(self, args: ItineraryDetailsArgs) -> ToolOutcome:
        it = self._itinerary(args.variant)
        details = self._describe(it, detailed=True)  # with the catalog descriptions, to answer from them
        return ToolOutcome(
            content=details,
            summary=f"La variante {details['nome_variante']} costa {eur(it.total_price)}, hotel {details['hotel']}.",
        )

    # --- Helpers -------------------------------------------------------------------------

    def _rehydrate(self, it: Itinerary):
        departure = it.view["flights"]["outbound"]["origin"]
        catalogs = load_catalogs(
            self.session, [it.country_code], departure, it.start_date, it.end_date + timedelta(days=1)
        )
        if not catalogs:
            raise ModificationError("Destinazione non più disponibile nel catalogo.")
        items = [(i.kind, i.ref_id, i.date) for i in it.items]
        plan = rehydrate(it.variant, it.country_code, it.budget_total, it.travelers, it.rooms, items, catalogs[0], {})
        return catalogs[0], plan

    def _relevance(self, request: str, reference: Itinerary) -> dict[str, float]:
        activities = list(self.session.scalars(select(Activity).where(Activity.country_code == reference.country_code)))
        index = self.service.index_factory(activities)
        similarity = index.similarities(request, [reference.country_code], reference.start_date.month)
        # The same audience adjustment as the planner (targets: famiglie, coppie...), so a swap "for the kids"
        # does not pick an activity aimed at young sporty people only because the words are close.
        return with_audience(similarity, activities, audience_of(self.service._requirements(self.conv)))

    def _replace(self, old: Itinerary, plan) -> Itinerary:
        departure = old.view["flights"]["outbound"]["origin"]
        errors = validate(draft_from_plan(plan, departure), SqlInventory(self.session))
        if errors:
            log.error("validator.rejected", extra={"variant": plan.variant, "errors": errors[:5], "source": "tool"})
            raise ModificationError("La modifica non rispetta budget o disponibilità.")
        country = self.session.get(Country, old.country_code)
        assert country is not None
        old.status = "discarded"
        new = self.service.save_plan(self.conv, plan, country, departure)
        self.session.flush()
        if Phase(self.conv.phase) == Phase.AWAITING_CONFIRMATION:
            change_phase(self.conv, Phase.PROPOSING)  # the selected proposal changed: choose again
        return new


def _program_day(d: dict, detailed: bool) -> dict:
    day: dict = {"giorno": d["day"], "data": d["date"]}
    if d.get("travel_note"):
        day["voli"] = d["travel_note"]
    if d["activity"] is None:
        day["giorno_di_viaggio"] = True  # ADR-0023: the flights leave no time for an activity
        return day
    day.update(
        {
            "attività": d["activity"]["name"],
            "categoria": d["activity"]["category"],
            "prezzo_a_persona": d["activity"]["price_per_person"],
            "durata_ore": d["activity"]["duration_hours"],
        }
    )
    if detailed:
        day["descrizione"] = d["activity"]["description"]
    return day


_WORDS = re.compile(r"[a-zà-ùþæðö]{4,}", re.IGNORECASE)
# Words that appear in many activity names and say nothing about which one is meant.
_GENERIC = {
    "nella",
    "nello",
    "della",
    "dello",
    "delle",
    "degli",
    "alla",
    "sulla",
    "dalla",
    "giorn",
    "visit",
    "tour",
    "guida",
    "passe",
    "serat",
    "corso",
    "lezio",
    "centr",
    "stori",
}


def name_match(query: str, name: str) -> float:
    """Share of the activity name's distinctive words (5-letter stems) that appear in the query."""
    words = {w.lower()[:5] for w in _WORDS.findall(name)} - _GENERIC
    said = {w.lower()[:5] for w in _WORDS.findall(query)}
    return len(words & said) / len(words) if words else 0.0


def named(query: str, name: str) -> float:
    """1 when the question names the activity (most of its distinctive words), else 0."""
    return 1.0 if name_match(query, name) >= 0.5 else 0.0
