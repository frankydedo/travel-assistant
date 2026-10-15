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
from app.textfmt import eur

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
    def _describe(it: Itinerary) -> dict:
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
            "budget_euro": it.budget_total,
            "programma": [
                {
                    "giorno": d["day"],
                    "data": d["date"],
                    "attività": d["activity"]["name"],
                    "categoria": d["activity"]["category"],
                    "prezzo_a_persona": d["activity"]["price_per_person"],
                }
                for d in v["days_plan"]
            ],
        }

    # --- Execution ---------------------------------------------------------------------

    def execute(self, call: ToolCall) -> ToolOutcome:
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
        if extraction.value.requirements.is_empty():
            if mentions_exact_date(args.change) or mentions_exact_date(self.service._last_user_text or ""):
                # Nothing to change: the orchestrator explains that dates are month-only (fixed text).
                return ToolOutcome(content={"ok": True}, summary="", terminal=True)
            return self._error(
                "Non ho capito quale requisito cambiare: chiedi all'utente di specificarlo.",
                user_text="Non ho capito cosa vuoi cambiare: dimmi quale requisito modificare (budget, mese, "
                "durata, partenza, numero di persone o interessi).",
            )
        self.service._apply_update(self.conv, current, extraction.value.requirements)
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
            f"con «{after.name}»: il nuovo totale è {eur(new.total_price)} su {eur(new.budget_total)}."
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
                "budget_euro": new.budget_total,
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
            f"({hotel.stars}★): il nuovo totale è {eur(new.total_price)} su {eur(new.budget_total)}."
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
                "budget_euro": new.budget_total,
            },
            summary=summary,
            itinerary_ids=[new.id],
        )

    # Look-ups: read only.

    def _search_activities(self, args: SearchActivitiesArgs) -> ToolOutcome:
        active = list(self.active().values())
        if not active:
            return self._error("Non ci sono proposte attive.")
        reference = active[0]
        relevance = self._relevance(args.query, reference)
        activities = self.session.scalars(select(Activity).where(Activity.country_code == reference.country_code))
        ranked = sorted(activities, key=lambda a: -relevance.get(a.id, 0.0))[:5]
        trip_months = {reference.start_date.month, reference.end_date.month}
        results = [
            {
                "attività": a.name,
                "categoria": CATEGORIES.get(a.category, a.category),
                "prezzo_a_persona": a.price,
                "disponibile_nel_periodo": bool(trip_months & set(a.months)),
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
        details = self._describe(it)
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
        return index.similarities(request, [reference.country_code], reference.start_date.month)

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
