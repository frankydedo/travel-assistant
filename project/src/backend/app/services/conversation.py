"""The orchestrator (ADR-0001): deterministic code that drives the conversation phases.

The interpreter understands and explains; this module decides: phase transitions, which countries are
feasible, which itineraries reach the user (only validated ones), what gets persisted.
"""

import calendar
import json
import logging
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace as dc_replace
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import SqlInventory, catalog_facts, load_catalogs, resolve_month
from app.config import Settings
from app.domain.phases import Phase, change_phase
from app.domain.planner import (
    CountryCatalog,
    GreedyPlanner,
    PlannedItinerary,
    Planner,
    PlanningRequest,
    minimum_cost,
)
from app.domain.requirements import (
    ANY_AIRPORT,
    CATEGORIES,
    MONTHS_IT,
    Destination,
    DestinationType,
    RequirementsUpdate,
    TripRequirements,
    keep_explicit_any,
    mentions_exact_date,
    validate_against_catalog,
)
from app.domain.validator import draft_from_plan, validate
from app.llm.base import LLMResult
from app.llm.gateway import AllProvidersFailed
from app.llm.grounding import strip_field_labels, ungrounded_amounts
from app.llm.interpreter import PROMPT_VERSION, Interpreter, missing_labels
from app.llm.mock import VARIANT_LABELS, VARIANT_WORDS, write_reply
from app.llm.registry import AI_PROVIDERS
from app.models import Activity, Conversation, Country, Itinerary, ItineraryItem, Message
from app.observability import get_observability
from app.rag.retriever import SemanticIndex, audience_of, score_activities, with_audience
from app.services.catalog_tools import SPECS as CATALOG_TOOLS
from app.services.catalog_tools import CatalogToolbox
from app.services.proposal_tools import SPECS as PROPOSAL_TOOLS
from app.services.proposal_tools import ProposalToolbox
from app.services.views import itinerary_view
from app.textfmt import budget_value, period_it

log = logging.getLogger(__name__)

GREETING = (
    "Ciao! Sono il tuo assistente di viaggio. Raccontami il viaggio che hai in mente: budget totale, "
    "destinazione (oppure «consigliami tu» o «ovunque»), cosa ti piace fare, mese, durata, da dove parti "
    "e quante persone siete. Puoi dirmi tutto insieme o un pezzo alla volta."
)
BOOKED_REPLY = (
    "Questo viaggio è già prenotato: lo trovi nella pagina Prenotazioni. Per organizzarne un altro apri "
    "una nuova conversazione."
)
EXACT_DATE_NOTICE = (
    "Nota: posso fissare solo il **mese** del viaggio, non il giorno esatto. La data di partenza la scelgo io "
    "tra quelle con voli e hotel disponibili nel mese, e la trovi indicata su ogni proposta. Se preferisci, "
    "posso cercare in un altro mese o con una durata diversa."
)
UNAVAILABLE_REPLY = "Il servizio di assistenza è momentaneamente non disponibile. Riprova tra poco."
# Written by code, never by the LLM (ADR-0016): a jailbreak cannot talk the refusal into an answer.
# Several fixed texts, rotated per conversation, so consecutive refusals do not repeat word for word.
OUT_OF_SCOPE_REPLIES = (
    "Sono un assistente AI per viaggi: la tua domanda è fuori dal mio ambito, quindi non posso rispondere.",
    "Mi dispiace, posso aiutarti solo con l'organizzazione del tuo viaggio: questa richiesta esce dal mio campo.",
    "Su questo non posso esserti d'aiuto: mi occupo soltanto di viaggi, itinerari e prenotazioni.",
    "Questa domanda non riguarda il viaggio che stiamo organizzando, quindi preferisco non rispondere.",
    "Sono specializzato in viaggi e non rispondo a richieste su altri argomenti.",
)
OUT_OF_SCOPE_NEXT_STEP = {
    Phase.COLLECTING_REQUIREMENTS: "Se vuoi, continuiamo a preparare il viaggio: raccontami cosa hai in mente.",
    Phase.PROPOSING: "Torniamo alle proposte: dimmi quale variante preferisci o cosa vuoi cambiare.",
    Phase.AWAITING_CONFIRMATION: "Quando vuoi, conferma la proposta scelta con il pulsante «Conferma e prenota».",
    Phase.BOOKED: "Il tuo viaggio è già prenotato: per organizzarne un altro apri una nuova conversazione.",
}
ACTIVE_STATUSES = ("proposed", "selected")
RELAXATION_MONTH_OFFSETS = (1, -1, 2, -2, 3, -3)
NEUTRAL_SCORE = 0.5
CHECK_CARDS_REPLY = (
    "Trovi prezzi e dettagli aggiornati nelle card delle proposte: dimmi quale preferisci o cosa cambiare."
)
# Choosing or booking a named variant, without asking to change it ("scelgo la bilanciata", "prenota la premium").
CHOICE_INTENT = (
    r"\b(scelgo|scegliamo|prendo|prendiamo|opto|optiamo|confermo|voglio la|vogliamo la|"
    r"prenota|prenotami|prenotala|prenotiamo|prenotate)\b"
)
# Not a choice: a change ("ma cambia..."), a negation ("non voglio la premium") or a question.
CHANGE_WORDS_IN_CHOICE = (
    r"\b(ma|però|cambi\w*|sostitu\w*|invece|senza|tranne|modific\w*|con)\b|\?|"
    r"\bnon (voglio|vogliamo|prendo|prendiamo|scelgo|scegliamo|prenot\w*)"
)
# Why each variant is what it is, written by code (the strategies of ADR-0003).
VARIANT_WHY = {
    "economy": "punta sul prezzo più basso",
    "balanced": "bilancia prezzo e qualità di hotel e attività",
    "premium": "punta su hotel e attività migliori",
}
MAX_TOOL_STEPS = 3  # bounded loop: the model cannot keep calling tools forever
TOOL_PROGRESS = {
    "swap_activity": "Cerco un'attività alternativa…",
    "change_hotel": "Cerco un altro hotel…",
    "search_activities": "Cerco nel catalogo…",
    "get_itinerary_details": "Recupero i dettagli…",
    "update_requirements": "Aggiorno i requisiti…",
}


class InvalidRequest(Exception):
    pass


def trip_start_dates(month_days: list[date], max_days: int) -> list[date]:
    """Assumption (README): the whole trip falls inside the requested month when possible; otherwise it
    starts in the month and may end in the next one."""
    if not month_days:
        return []
    last = month_days[-1].replace(day=calendar.monthrange(month_days[-1].year, month_days[-1].month)[1])
    inside = [d for d in month_days if d + timedelta(days=max_days - 1) <= last]
    return inside or month_days


class ConversationService:
    def __init__(
        self,
        session: Session,
        interpreter: Interpreter,
        index_factory: Callable[[list[Activity]], SemanticIndex],
        settings: Settings,
        planner: Planner | None = None,
        today: date | None = None,
    ):
        self.session = session
        self.interpreter = interpreter
        self.index_factory = index_factory
        self.settings = settings
        self.planner = planner or GreedyPlanner()
        self.today = today
        self.emit: Callable[[str, dict], None] = lambda event, data: None  # SSE sink (ADR-0011)
        self._last_user_text = ""
        self.tracer = get_observability()
        self._trace_id: str | None = None

    def _progress(self, stage: str, message: str) -> None:
        self.emit("progress", {"stage": stage, "message": message})

    def _write(self, kind: str, facts: dict) -> LLMResult:
        """Generate a reply, streaming tokens (and provider switches) to the SSE sink."""
        self._progress("writing", "Preparo la risposta…")
        facts = {**facts, "ultimo_messaggio_utente": self._last_user_text}
        result = self.interpreter.write(
            kind,
            facts,
            on_token=lambda text: self.emit("token", {"text": text}),
            on_reset=lambda: self.emit("reset", {}),
            on_attempt=lambda provider, model: self.emit(
                "provider", {"provider": provider, "model": model, "ai_generated": provider in AI_PROVIDERS}
            ),
        )
        if result.provider not in AI_PROVIDERS:
            return result
        if wrong := ungrounded_amounts(result.text, facts):
            return self._replace_ungrounded(result, wrong, write_reply(kind, facts), task=f"reply:{kind}")
        if (clean := strip_field_labels(result.text)) != result.text:
            self.emit("reset", {})  # the reply was already streamed with the labels
            self.emit("token", {"text": clean})
            result = dc_replace(result, text=clean)
        return result

    def _replace_ungrounded(
        self, result: LLMResult, wrong: list[int], text: str, task: str, streamed: bool = True
    ) -> LLMResult:
        """ADR-0025: an amount the code did not compute never reaches the user. The reply written by code
        replaces the LLM's one (SYSTEM tag); the event goes to the logs and to the trace."""
        log.warning("llm.ungrounded_amount", extra={"task": task, "provider": result.provider, "amounts": wrong})
        with self.tracer.observation(
            "guardrail.ungrounded_amount", as_type="guardrail", level="WARNING", input=result.text, output=text
        ):
            pass
        if streamed:
            self.emit("reset", {})
        self.emit("provider", {"provider": "SYSTEM", "model": None, "ai_generated": False})
        self.emit("token", {"text": text})
        return dc_replace(result, text=text, provider="SYSTEM", model="")

    # --- Public API -------------------------------------------------------------------

    def create(self, user_id: str) -> Conversation:
        conv = Conversation(
            user_id=user_id,
            phase=Phase.COLLECTING_REQUIREMENTS,
            requirements=TripRequirements().model_dump(mode="json"),
        )
        self.session.add(conv)
        self.session.flush()
        self._add_message(conv, "assistant", GREETING, provider="SYSTEM")
        self.session.commit()
        return conv

    def handle_message(self, conv: Conversation, text: str) -> None:
        with self._turn("chat_turn", conv):
            self._handle_message(conv, text)

    def _handle_message(self, conv: Conversation, text: str) -> None:
        self._add_message(conv, "user", text)
        self._last_user_text = text
        self._progress("interpreting", "Sto leggendo la tua richiesta…")
        if conv.title is None:
            conv.title = text.strip()[:60]
        try:
            phase = Phase(conv.phase)
            if phase == Phase.BOOKED:
                self._add_message(conv, "assistant", BOOKED_REPLY, provider="SYSTEM")
            elif phase == Phase.COLLECTING_REQUIREMENTS:
                current = self._requirements(conv)
                interpreted = self.interpreter.extract_requirements(text, current, self._history(conv))
                value = interpreted.value
                if value.catalog_question:
                    self._catalog_reply(conv, current, value.requirements, text)
                elif not value.in_scope and value.requirements.is_empty():
                    self._refuse(conv)
                else:
                    self._apply_update(conv, current, value.requirements)
            else:
                self._proposal_reply(conv, text)
            if phase != Phase.BOOKED and mentions_exact_date(text) and not self._refused(conv):
                self._add_message(conv, "assistant", EXACT_DATE_NOTICE, provider="SYSTEM")
        except AllProvidersFailed:
            log.exception("llm.all_providers_failed")
            self._add_message(conv, "assistant", UNAVAILABLE_REPLY, provider="SYSTEM")
        self.session.commit()

    def select(self, conv: Conversation, itinerary: Itinerary) -> None:
        with self._turn("select_itinerary", conv):
            self._select(conv, itinerary)

    def _select(self, conv: Conversation, itinerary: Itinerary) -> None:
        if Phase(conv.phase) not in (Phase.PROPOSING, Phase.AWAITING_CONFIRMATION):
            raise InvalidRequest("La conversazione non è nella fase di proposta.")
        if itinerary.status not in ACTIVE_STATUSES:
            raise InvalidRequest("Questa proposta non è più valida.")
        for other in self._active_itineraries(conv):
            if other.status == "selected" and other.id != itinerary.id:
                other.status = "proposed"
        itinerary.status = "selected"
        change_phase(conv, Phase.AWAITING_CONFIRMATION)
        view = itinerary.view
        result = self._write(
            "confirm_summary",
            {
                "variant": itinerary.variant,
                "nome_variante": VARIANT_LABELS[itinerary.variant],
                "destination": view["destination"],
                "start_date": view["start_date"],
                "end_date": view["end_date"],
                "periodo": period_it(view["start_date"], view["end_date"]),
                "days": view["days"],
                "travelers": view["travelers"],
                "total_price": itinerary.total_price,
            },
        )
        self._add_message(
            conv,
            "assistant",
            result.text,
            result=result,
            ui={"type": "confirm_booking", "itinerary_id": itinerary.id},
        )
        self.session.commit()

    def replan_after_conflict(self, conv: Conversation) -> None:
        """Availability changed between proposal and booking: plan again with fresh inventory."""
        with self._turn("replan_after_conflict", conv):
            self._replan_after_conflict(conv)

    def _replan_after_conflict(self, conv: Conversation) -> None:
        req = self._requirements(conv)
        self._add_message(
            conv,
            "assistant",
            "Nel frattempo la disponibilità è cambiata e la proposta scelta non è più prenotabile. "
            "Ho ricalcolato le alternative con i dati aggiornati.",
            provider="SYSTEM",
        )
        try:
            self._propose(conv, req)
        except AllProvidersFailed:
            self._add_message(conv, "assistant", UNAVAILABLE_REPLY, provider="SYSTEM")
        self.session.commit()

    # --- Phases ---------------------------------------------------------------------------

    def _proposal_reply(self, conv: Conversation, text: str) -> None:
        """Bounded tool loop inside the proposal phase (ADR-0001): the LLM picks tools, the code validates
        and runs them. Terminal tools hand control back to the orchestrator, which writes the reply."""
        toolbox = ProposalToolbox(self, conv)
        followups: list[dict] = []
        summaries: list[str] = []
        new_ids: list[str] = []
        final: LLMResult | None = None
        for _ in range(MAX_TOOL_STEPS):
            result = self.interpreter.proposal_step(
                text, toolbox.context(), PROPOSAL_TOOLS, followups, summaries, conv.phase
            )
            if not result.tool_calls:
                final = result
                break
            followups.append(_assistant_tool_turn(result))
            for call in result.tool_calls:
                self._progress("tool", TOOL_PROGRESS.get(call.name, "Elaboro la richiesta…"))
                outcome = toolbox.execute(call)
                if outcome.terminal:
                    return  # select / update / refuse: their flow already wrote the reply
                if outcome.summary and outcome.summary not in summaries:
                    summaries.append(outcome.summary)
                new_ids += outcome.itinerary_ids
                followups.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(outcome.content, ensure_ascii=False, default=str),
                    }
                )
        no_tools_ran = not followups  # a modification already made must keep its own reply and card
        if final is not None and final.text and no_tools_ran and (chosen := self._explicit_choice(conv, text)):
            # The user named a variant to choose or book and the model only answered in words: without the
            # selection the confirm button never appears (ADR-0006). Code makes the choice it was asked for.
            log.info("proposal.selection_forced", extra={"variant": chosen.variant})
            self._select(conv, chosen)
            return
        if final is not None and final.text:
            # Checked before anything is streamed: the proposal step does not stream, so an unchecked amount
            # never reaches the browser (ADR-0025).
            grounding = [toolbox.context(), *(m["content"] for m in followups if m.get("role") == "tool"), summaries]
            if final.provider in AI_PROVIDERS and (wrong := ungrounded_amounts(final.text, *grounding)):
                fallback = " ".join(summaries) or CHECK_CARDS_REPLY
                final = self._replace_ungrounded(final, wrong, fallback, task="proposal_tools", streamed=False)
            else:
                final = dc_replace(final, text=strip_field_labels(final.text))
                self.emit(
                    "provider",
                    {"provider": final.provider, "model": final.model, "ai_generated": final.provider in AI_PROVIDERS},
                )
                self.emit("token", {"text": final.text})
            self._add_message(conv, "assistant", final.text, result=final, itinerary_ids=new_ids)
        else:
            # Loop exhausted or empty answer: report what the code did, in its own words.
            reply = " ".join(summaries) or "Puoi dirmi quale variante preferisci o cosa vuoi cambiare?"
            self.emit("provider", {"provider": "SYSTEM", "model": None, "ai_generated": False})
            self.emit("token", {"text": reply})
            self._add_message(conv, "assistant", reply, provider="SYSTEM", itinerary_ids=new_ids)

    def _merge(
        self, conv: Conversation, current: TripRequirements, update: RequirementsUpdate
    ) -> tuple[TripRequirements, RequirementsUpdate, list[str]]:
        update = keep_explicit_any(update, self._last_user_text, current.missing_fields())
        merged = current.merge(update)
        merged, issues = validate_against_catalog(merged, catalog_facts(self.session, self.settings.max_trip_days))
        conv.requirements = merged.model_dump(mode="json")
        return merged, update, issues

    def _catalog_reply(
        self, conv: Conversation, current: TripRequirements, update: RequirementsUpdate, text: str
    ) -> None:
        """A question about the catalog while collecting (ADR-0026): the requirements said in the same
        message are recorded as usual, read-only tools answer the question, and the reply also asks for
        what is still missing. Complete requirements then lead to the proposals as usual."""
        merged, _, issues = self._merge(conv, current, update)
        missing = missing_labels(merged.missing_fields())[:3]  # one natural question, not a form
        toolbox = CatalogToolbox(self, conv)
        followups: list[dict] = []
        summaries: list[str] = list(issues)
        final: LLMResult | None = None
        for _ in range(MAX_TOOL_STEPS):
            result = self.interpreter.catalog_step(
                text, merged.model_dump(mode="json"), missing, CATALOG_TOOLS, followups, summaries
            )
            if not result.tool_calls:
                final = result
                break
            followups.append(_assistant_tool_turn(result))
            for call in result.tool_calls:
                self._progress("tool", "Consulto il catalogo…")
                outcome = toolbox.execute(call)
                if outcome.summary and outcome.summary not in summaries:
                    summaries.append(outcome.summary)
                followups.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(outcome.content, ensure_ascii=False, default=str),
                    }
                )
        fallback = " ".join(summaries) or "Posso darti informazioni su destinazioni, aeroporti, hotel e attività."
        if final is not None and final.text:
            grounding = [*(m["content"] for m in followups if m.get("role") == "tool"), summaries, merged.model_dump()]
            if final.provider in AI_PROVIDERS and (wrong := ungrounded_amounts(final.text, *grounding)):
                final = self._replace_ungrounded(final, wrong, fallback, task="catalog_tools", streamed=False)
            else:
                final = dc_replace(final, text=strip_field_labels(final.text))
                self.emit(
                    "provider",
                    {"provider": final.provider, "model": final.model, "ai_generated": final.provider in AI_PROVIDERS},
                )
                self.emit("token", {"text": final.text})
            self._add_message(conv, "assistant", final.text, result=final)
        else:
            self.emit("provider", {"provider": "SYSTEM", "model": None, "ai_generated": False})
            self.emit("token", {"text": fallback})
            self._add_message(conv, "assistant", fallback, provider="SYSTEM")
        if merged.is_complete() and not issues:
            self._propose(conv, merged)

    def _apply_update(self, conv: Conversation, current: TripRequirements, update: RequirementsUpdate) -> None:
        merged, update, issues = self._merge(conv, current, update)
        if issues or not merged.is_complete():
            change_phase(conv, Phase.COLLECTING_REQUIREMENTS)
            missing = merged.missing_fields()
            result = self._write(
                "ask_missing",
                {
                    "missing_fields": missing,
                    "missing": missing_labels(missing),
                    "issues": issues,
                    "known": not update.is_empty(),
                    "già_noto": self._known_requirements(merged),
                },
            )
            self._add_message(conv, "assistant", result.text, result=result)
            return
        self._propose(conv, merged)

    def _propose(self, conv: Conversation, req: TripRequirements) -> None:
        assert req.is_complete() and req.destination and req.duration and req.month and req.preferences
        start_dates = trip_start_dates(resolve_month(self.session, req.month, self.today), req.duration.max_days)
        if not start_dates:
            self._infeasible(conv, req, "il mese richiesto non è coperto dal nostro catalogo.", [])
            return

        destination_reason = None
        anywhere = req.destination.type == DestinationType.ANYWHERE
        if req.destination.type == DestinationType.SUGGEST:
            chosen = self._suggest(conv, req, start_dates)
            if chosen is None:
                return
            req, codes, destination_reason = chosen
        elif req.destination.type == DestinationType.ANYWHERE:
            codes = sorted(self.session.scalars(select(Country.code)))
        else:
            codes = [req.destination.country_code]  # type: ignore[list-item]

        self._progress("planning", "Cerco voli, hotel e attività…")
        started = time.perf_counter()
        request = self._planning_request(req, start_dates, codes)
        with self.tracer.observation(
            "planner.greedy",
            as_type="chain",
            input={
                "countries": codes,
                "start_dates": len(start_dates),
                "budget": req.budget_total,
                "days": [req.duration.min_days, req.duration.max_days],
                "travelers": req.travelers,
            },
        ) as span:
            catalogs = self._load(codes, req, start_dates)
            plans = self.planner.plan(request, catalogs)
            span.update(
                output=[
                    {"variant": p.variant, "country": p.country_code, "days": p.days, "total": p.total_price}
                    for p in plans
                ]
            )
        self._progress("validating", "Verifico budget e disponibilità…")
        valid = []
        inventory = SqlInventory(self.session)
        for plan in plans:
            errors = validate(draft_from_plan(plan, plan.outbound.origin), inventory)
            if errors:
                # A planner bug caught by the second line of defence: never shown to the user.
                log.error("validator.rejected", extra={"variant": plan.variant, "errors": errors[:5]})
                with self.tracer.observation(
                    "validator.rejected",
                    as_type="guardrail",
                    level="ERROR",
                    input={"variant": plan.variant},
                    output={"errors": errors[:5]},
                ):
                    pass
                continue
            valid.append(plan)
        log.info(
            "planner.completed",
            extra={
                "countries": codes,
                "start_dates": len(start_dates),
                "variants_planned": len(plans),
                "variants_valid": len(valid),
                "duration_ms": round((time.perf_counter() - started) * 1000),
            },
        )
        if not valid:
            self._infeasible(conv, req, None, codes, start_dates)
            return

        for old in self._active_itineraries(conv):
            old.status = "discarded"
        countries = {c.code: c for c in self.session.scalars(select(Country).where(Country.code.in_(codes)))}
        saved = [self.save_plan(conv, plan, countries[plan.country_code], plan.outbound.origin) for plan in valid]
        self.session.flush()

        change_phase(conv, Phase.PROPOSING)
        names = sorted({countries[p.country_code].name for p in valid})
        conv.title = f"{' / '.join(names)} · {MONTHS_IT[req.month - 1]}"
        result = self._write(
            "present_itineraries",
            {
                "destination_reason": destination_reason,
                "decisioni_prese": self._planning_choices(req, anywhere, codes),
                "varianti_mancanti": self._missing_variants({it.variant for it in saved}),
                "variants": [
                    {
                        "variant": it.variant,
                        "nome_variante": VARIANT_LABELS[it.variant],
                        "perché": VARIANT_WHY[it.variant],
                        "country": it.view["country_name"],
                        "destination": it.view["destination"],
                        "days": it.view["days"],
                        "start_date": it.view["start_date"],
                        "periodo": period_it(it.view["start_date"], it.view["end_date"]),
                        "total_price": it.total_price,
                        "budget": budget_value(it.budget_total),
                        "departure_airport": it.view["flights"]["outbound"]["origin"],
                        "hotel": it.view["hotel"]["name"],
                        "stars": it.view["hotel"]["stars"],
                        "top_activities": [d["activity"]["name"] for d in it.view["days_plan"] if d["activity"]][:3],
                        "giorni_di_viaggio": [
                            f"il giorno {d['day']} di questa variante è senza attività ({d['travel_note']})"
                            for d in it.view["days_plan"]
                            if d.get("travel_day")
                        ],
                    }
                    for it in saved
                ],
            },
        )
        self._add_message(conv, "assistant", result.text, result=result, itinerary_ids=[it.id for it in saved])

    def _known_requirements(self, req: TripRequirements) -> list[str]:
        """What has been understood so far, in words: the question can acknowledge it before asking."""
        known: list[str] = []
        if req.budget_total is not None:
            known.append("budget illimitato" if req.budget_limit is None else f"budget {req.budget_limit} €")
        if req.destination is not None:
            if req.destination.type == DestinationType.SUGGEST:
                known.append("meta da consigliare")
            elif req.destination.type == DestinationType.ANYWHERE:
                known.append("meta: ovunque")
            elif (country := self.session.get(Country, req.destination.country_code)) is not None:
                known.append(f"meta: {country.name}")
        if req.preferences is not None:
            if req.preferences.none:
                known.append("nessuna preferenza sulle attività")
            else:
                known.append(req.preferences.notes or ", ".join(CATEGORIES[c] for c in req.preferences.categories))
        if req.month is not None:
            known.append(MONTHS_IT[req.month - 1])
        if req.duration is not None:
            d = req.duration
            known.append(f"{d.min_days} giorni" if d.min_days == d.max_days else f"{d.min_days}-{d.max_days} giorni")
        if req.departure_airport is not None:
            known.append(
                "partenza da qualsiasi aeroporto" if req.any_airport else f"partenza da {req.departure_airport}"
            )
        if req.travelers is not None:
            known.append(f"{req.travelers} {'persona' if req.travelers == 1 else 'persone'}")
        return known

    def _missing_variants(self, proposed: set[str]) -> list[str]:
        """Why a variant is absent, so the reply can say it instead of silently showing two (ADR-0025)."""
        reasons = getattr(self.planner, "missing", {})
        notes = []
        for variant in ("economy", "balanced", "premium"):
            if variant in proposed:
                continue
            why = reasons.get(variant, "")
            if why.startswith("same_as:"):
                other = VARIANT_LABELS[why.removeprefix("same_as:")]
                notes.append(
                    f"La {VARIANT_LABELS[variant]} coinciderebbe con la {other}: con questo budget non c'è "
                    "un'alternativa diversa."
                )
            else:
                notes.append(f"Per la {VARIANT_LABELS[variant]} non c'è un itinerario possibile con questi requisiti.")
        return notes

    def _planning_choices(self, req: TripRequirements, anywhere: bool, codes: list[str]) -> list[str]:
        """What the code decided on the user's behalf for the "any" values, in words (ADR-0021, ADR-0022):
        the reply explains these choices instead of just listing the variants."""
        choices: list[str] = []
        if req.budget_limit is None:
            choices.append(
                "Budget illimitato: nessun limite di spesa, contano solo le disponibilità; la Bilanciata pesa il "
                "prezzo rispetto al costo della Premium."
            )
        if anywhere:
            names = sorted(c.name for c in self.session.scalars(select(Country).where(Country.code.in_(codes))))
            choices.append(
                f"Destinazione «ovunque»: ho confrontato {len(names)} paesi ({', '.join(names)}) e, quando "
                "possibile, ogni variante porta in un paese diverso."
            )
        if req.any_airport:
            choices.append(
                "Partenza da qualsiasi aeroporto: ho confrontato Roma Fiumicino, Milano Malpensa e Napoli, e ogni "
                "variante parte da quello che le conviene di più."
            )
        if req.preferences is not None and req.preferences.none:
            choices.append("Nessuna preferenza sulle attività: a parità di interesse decide il prezzo.")
        return choices

    def _suggest(
        self, conv: Conversation, req: TripRequirements, start_dates: list[date]
    ) -> tuple[TripRequirements, list[str], str] | None:
        """ "Consigliami tu": code finds the feasible countries, the LLM picks one of them."""
        all_codes = sorted(self.session.scalars(select(Country.code)))
        catalogs = self._load(all_codes, req, start_dates)
        request = self._planning_request(req, start_dates, [], scored=False)
        costs: dict[str, int | None] = {}
        for c in catalogs:  # with "any airport" a country has one catalog per departure airport
            cost = minimum_cost(request, c)
            if cost is not None and (costs.get(c.code) is None or cost < costs[c.code]):  # type: ignore[operator]
                costs[c.code] = cost
            costs.setdefault(c.code, None)
        budget = req.budget_limit
        feasible_codes = [
            code for code, cost in costs.items() if cost is not None and (budget is None or cost <= budget)
        ]
        if not feasible_codes:
            self._infeasible(conv, req, None, all_codes, start_dates)
            return None
        scores = self._scores(req, feasible_codes)
        rows = self.session.execute(
            select(Activity.id, Activity.country_code, Activity.name).where(Activity.country_code.in_(feasible_codes))
        )
        activity_country, activity_name = {}, {}
        for aid, code, name in rows:
            activity_country[aid], activity_name[aid] = code, name
        countries = {c.code: c for c in self.session.scalars(select(Country).where(Country.code.in_(feasible_codes)))}
        options = []
        for code in feasible_codes:
            ranked = sorted(((s, aid) for aid, s in scores.items() if activity_country.get(aid) == code), reverse=True)[
                :5
            ]
            top = [s for s, _ in ranked]
            options.append(
                {
                    "code": code,
                    "name": countries[code].name,
                    "destination": countries[code].destination,
                    "description": countries[code].description,
                    "min_cost": costs[code],
                    "preference_score": round(sum(top) / len(top), 3) if top else 0.0,
                    "attività_adatte": [activity_name[aid] for _, aid in ranked[:3]],
                }
            )
        choice = self.interpreter.choose_destination(options, req.preferences.model_dump())  # type: ignore[union-attr]
        code = choice.value.country_code.upper()
        reason = choice.value.reason
        if code not in feasible_codes:
            # The LLM must pick among feasible countries only: fall back to the best deterministic score.
            log.warning("suggest.non_feasible_choice", extra={"suggested": code, "feasible": feasible_codes})
            best = max(options, key=lambda o: (o["preference_score"], -o["min_cost"]))
            code, reason = best["code"], f"Ti consiglio {best['name']}: è la meta più adatta che rientra nel budget."
        req = req.model_copy(update={"destination": Destination(type=DestinationType.COUNTRY, country_code=code)})
        conv.requirements = req.model_dump(mode="json")
        return req, [code], reason

    def _infeasible(
        self,
        conv: Conversation,
        req: TripRequirements,
        reason: str | None,
        codes: list[str],
        start_dates: list[date] | None = None,
    ) -> None:
        """No valid itinerary: find which constraint blocks and which relaxations would work."""
        log.info("planner.infeasible", extra={"countries": codes, "reason_given": reason is not None})
        alternatives: list[str] = []
        if reason is None and start_dates:
            catalogs = self._load(codes, req, start_dates)
            request = self._planning_request(req, start_dates, [], scored=False)
            costs = [c for c in (minimum_cost(request, cat) for cat in catalogs) if c is not None]
            lowest = min(costs) if costs else None
            budget = req.budget_limit
            if lowest is None:
                reason = "non ci sono abbastanza disponibilità (voli, hotel o attività) nelle date richieste."
            elif budget is not None and lowest > budget:
                reason = f"il viaggio più economico possibile costa circa {lowest} €, oltre il budget di {budget} €."
                alternatives.append(f"aumentare il budget ad almeno {lowest} €")
            else:
                reason = "non riesco a combinare voli, hotel e attività distinte per ogni giorno entro il budget."
            alternatives += self._relaxations(req, codes, start_dates)
        change_phase(conv, Phase.COLLECTING_REQUIREMENTS)
        result = self._write("infeasible", {"reason": reason, "alternatives": alternatives})
        self._add_message(conv, "assistant", result.text, result=result)

    def _relaxations(self, req: TripRequirements, codes: list[str], start_dates: list[date]) -> list[str]:
        assert req.duration and req.month and req.destination and req.budget_total
        budget = req.budget_limit
        found: list[str] = []

        def fits(cost: int | None) -> bool:
            return cost is not None and (budget is None or cost <= budget)

        def cheapest(r: TripRequirements, dates: list[date], country_codes: list[str]) -> int | None:
            catalogs = self._load(country_codes, r, dates)
            request = self._planning_request(r, dates, [], scored=False)
            values = [c for c in (minimum_cost(request, cat) for cat in catalogs) if c is not None]
            return min(values) if values else None

        for days in range(req.duration.min_days - 1, 1, -1):
            shorter = req.model_copy(
                update={"duration": req.duration.model_copy(update={"min_days": days, "max_days": days})}
            )
            cost = cheapest(shorter, start_dates, codes)
            if fits(cost):
                found.append(f"ridurre la durata a {days} giorni (da circa {cost} €)")
                break
        months = 0
        for offset in RELAXATION_MONTH_OFFSETS:
            month = (req.month - 1 + offset) % 12 + 1
            dates = trip_start_dates(resolve_month(self.session, month, self.today), req.duration.max_days)
            if not dates:
                continue
            cost = cheapest(req.model_copy(update={"month": month}), dates, codes)
            if fits(cost):
                found.append(f"partire a {MONTHS_IT[month - 1]} (da circa {cost} €)")
                months += 1
                if months == 2:
                    break
        if req.destination.type == DestinationType.COUNTRY:
            others = [c for c in sorted(self.session.scalars(select(Country.code))) if c not in codes]
            names = {c.code: c.name for c in self.session.scalars(select(Country))}
            options = []
            for code in others:
                cost = cheapest(req, start_dates, [code])
                if fits(cost):
                    options.append((cost, code))
            for cost, code in sorted(options)[:2]:
                found.append(f"scegliere {names[code]} (da circa {cost} €)")
        return found

    # --- Helpers ----------------------------------------------------------------------------

    @contextmanager
    def _turn(self, name: str, conv: Conversation) -> Iterator[None]:
        """One Langfuse trace per turn; nested calls (e.g. a tool selecting a variant) join it."""
        if self._trace_id is not None:
            yield
            return
        with self.tracer.turn(name, conv.user_id, conv.id, conv.phase, PROMPT_VERSION) as trace_id:
            self._trace_id = trace_id
            try:
                yield
            finally:
                self._trace_id = None

    def save_plan(self, conv: Conversation, plan: PlannedItinerary, country: Country, departure: str) -> Itinerary:
        """Persist a validated plan as a new proposed itinerary (view snapshot + items)."""
        itinerary = Itinerary(
            conversation_id=conv.id,
            user_id=conv.user_id,
            variant=plan.variant,
            status="proposed",
            country_code=plan.country_code,
            start_date=plan.start_date,
            end_date=plan.end_date,
            travelers=plan.travelers,
            rooms=plan.rooms,
            total_price=plan.total_price,
            budget_total=plan.budget,
            view=itinerary_view(plan, country.name, country.destination),
        )
        for position, item in enumerate(draft_from_plan(plan, departure).items):
            itinerary.items.append(
                ItineraryItem(
                    position=position,
                    kind=item.kind,
                    ref_id=item.ref_id,
                    date=item.date,
                    unit_price=item.unit_price,
                    quantity=item.quantity,
                    subtotal=item.subtotal,
                )
            )
        self.session.add(itinerary)
        return itinerary

    def _refuse(self, conv: Conversation) -> None:
        """Out-of-scope message: fixed reply, phase and requirements untouched."""
        log.info("guardrail.out_of_scope", extra={"phase": conv.phase})
        with self.tracer.observation(
            "guardrail.out_of_scope", as_type="guardrail", input=self._last_user_text, output="refused"
        ):
            pass
        previous = sum(1 for m in conv.messages if m.role == "assistant" and m.content.startswith(OUT_OF_SCOPE_REPLIES))
        reply = OUT_OF_SCOPE_REPLIES[previous % len(OUT_OF_SCOPE_REPLIES)]
        self._add_message(conv, "assistant", f"{reply} {OUT_OF_SCOPE_NEXT_STEP[Phase(conv.phase)]}", provider="SYSTEM")

    def _explicit_choice(self, conv: Conversation, text: str) -> Itinerary | None:
        """A message that clearly chooses (or asks to book) exactly one of the active variants."""
        lowered = text.lower()
        if not re.search(CHOICE_INTENT, lowered) or re.search(CHANGE_WORDS_IN_CHOICE, lowered):
            return None
        active = {it.variant: it for it in self._active_itineraries(conv) if it.status == "proposed"}
        named = [v for v, words in VARIANT_WORDS.items() if v in active and any(w in lowered for w in words)]
        return active[named[0]] if len(named) == 1 else None

    def _refused(self, conv: Conversation) -> bool:
        last = next((m for m in reversed(conv.messages) if m.role == "assistant"), None)
        return last is not None and last.content.startswith(OUT_OF_SCOPE_REPLIES)

    def _planning_request(
        self, req: TripRequirements, start_dates: list[date], codes: list[str], scored: bool = True
    ) -> PlanningRequest:
        assert req.budget_total and req.travelers and req.duration
        return PlanningRequest(
            budget=req.budget_limit,
            travelers=req.travelers,
            start_dates=start_dates,
            min_days=req.duration.min_days,
            max_days=req.duration.max_days,
            activity_scores=self._scores(req, codes) if scored and codes else {},
            distinct_countries=req.destination is not None and req.destination.type == DestinationType.ANYWHERE,
        )

    def _scores(self, req: TripRequirements, codes: list[str]) -> dict[str, float]:
        assert req.preferences and req.month
        activities = list(self.session.scalars(select(Activity).where(Activity.country_code.in_(codes))))
        audience = audience_of(req)
        if req.preferences.none:
            # "Nessuna preferenza" (ADR-0021): every activity is equally welcome, cost and variant decide.
            return with_audience({a.id: NEUTRAL_SCORE for a in activities}, activities, audience)
        index = self.index_factory(activities)
        with self.tracer.observation(
            "rag.score_activities",
            as_type="retriever",
            input={"preferences": req.preferences.model_dump(), "countries": codes, "month": req.month},
        ) as span:
            scores = with_audience(
                score_activities(index, req.preferences, activities, codes, req.month), activities, audience
            )
            names = {a.id: a.name for a in activities}
            top = sorted(scores.items(), key=lambda kv: -kv[1])[:5]
            span.update(output=[{"activity": names[aid], "score": score} for aid, score in top])
        return scores

    def _load(self, codes: list[str], req: TripRequirements, start_dates: list[date]) -> list[CountryCatalog]:
        assert req.departure_airport and req.duration
        date_to = start_dates[-1] + timedelta(days=req.duration.max_days)
        airports = (
            sorted(catalog_facts(self.session, self.settings.max_trip_days).departure_airports)
            if req.departure_airport == ANY_AIRPORT
            else [req.departure_airport]
        )
        # "Any airport" (ADR-0021): one catalog per departure airport, the planner compares them all.
        return [c for a in airports for c in load_catalogs(self.session, codes, a, start_dates[0], date_to)]

    def _requirements(self, conv: Conversation) -> TripRequirements:
        return TripRequirements.model_validate(conv.requirements)

    def _active_itineraries(self, conv: Conversation) -> list[Itinerary]:
        return list(
            self.session.scalars(
                select(Itinerary).where(Itinerary.conversation_id == conv.id, Itinerary.status.in_(ACTIVE_STATUSES))
            )
        )

    def _history(self, conv: Conversation) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in conv.messages[-8:]]

    def _add_message(
        self,
        conv: Conversation,
        role: str,
        content: str,
        result: LLMResult | None = None,
        provider: str | None = None,
        itinerary_ids: list[str] | None = None,
        ui: dict | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conv.id,
            seq=len(conv.messages) + 1,
            role=role,
            content=content,
            provider=result.provider if result else provider,
            model=result.model if result else None,
            itinerary_ids=itinerary_ids or [],
            ui=ui,
            trace_id=self._trace_id,
        )
        conv.messages.append(message)
        return message


def _assistant_tool_turn(result: LLMResult) -> dict:
    """The assistant turn that asked for tools, as it goes back to the model in the next step."""
    return {
        "role": "assistant",
        "content": result.text or None,
        "tool_calls": [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.name, "arguments": json.dumps(c.arguments, ensure_ascii=False)},
                "_provider": c.provider,  # provider-specific fields are re-attached for it only
                "_extra": c.extra,
            }
            for c in result.tool_calls
        ],
    }
