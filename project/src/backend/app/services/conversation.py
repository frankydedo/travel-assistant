"""The orchestrator (ADR-0001): deterministic code that drives the conversation phases.

The interpreter understands and explains; this module decides: phase transitions, which countries are
feasible, which itineraries reach the user (only validated ones), what gets persisted.
"""

import calendar
import json
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
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
    MONTHS_IT,
    Destination,
    DestinationType,
    RequirementsUpdate,
    TripRequirements,
    validate_against_catalog,
)
from app.domain.validator import draft_from_plan, validate
from app.llm.base import LLMResult
from app.llm.gateway import AllProvidersFailed
from app.llm.interpreter import PROMPT_VERSION, Interpreter, missing_labels
from app.llm.mock import VARIANT_LABELS
from app.llm.registry import AI_PROVIDERS
from app.models import Activity, Conversation, Country, Itinerary, ItineraryItem, Message
from app.observability import get_observability
from app.rag.retriever import SemanticIndex, score_activities
from app.services.proposal_tools import SPECS as PROPOSAL_TOOLS
from app.services.proposal_tools import ProposalToolbox
from app.services.views import itinerary_view

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
        return self.interpreter.write(
            kind,
            {**facts, "ultimo_messaggio_utente": self._last_user_text},
            on_token=lambda text: self.emit("token", {"text": text}),
            on_reset=lambda: self.emit("reset", {}),
            on_attempt=lambda provider, model: self.emit(
                "provider", {"provider": provider, "model": model, "ai_generated": provider in AI_PROVIDERS}
            ),
        )

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
                if not interpreted.value.in_scope and interpreted.value.requirements.is_empty():
                    self._refuse(conv)
                else:
                    self._apply_update(conv, current, interpreted.value.requirements)
            else:
                self._proposal_reply(conv, text)
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
            followups.append(
                {
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
            )
            for call in result.tool_calls:
                self._progress("tool", TOOL_PROGRESS.get(call.name, "Elaboro la richiesta…"))
                outcome = toolbox.execute(call)
                if outcome.terminal:
                    return  # select / update / refuse: their flow already wrote the reply
                summaries.append(outcome.summary)
                new_ids += outcome.itinerary_ids
                followups.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(outcome.content, ensure_ascii=False, default=str),
                    }
                )
        if final is not None and final.text:
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

    def _apply_update(self, conv: Conversation, current: TripRequirements, update: RequirementsUpdate) -> None:
        merged = current.merge(update)
        merged, issues = validate_against_catalog(merged, catalog_facts(self.session, self.settings.max_trip_days))
        conv.requirements = merged.model_dump(mode="json")
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
            errors = validate(draft_from_plan(plan, req.departure_airport), inventory)  # type: ignore[arg-type]
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
        saved = [self.save_plan(conv, plan, countries[plan.country_code], req.departure_airport) for plan in valid]
        self.session.flush()

        change_phase(conv, Phase.PROPOSING)
        names = sorted({countries[p.country_code].name for p in valid})
        conv.title = f"{' / '.join(names)} · {MONTHS_IT[req.month - 1]}"
        result = self._write(
            "present_itineraries",
            {
                "destination_reason": destination_reason,
                "variants": [
                    {
                        "variant": it.variant,
                        "nome_variante": VARIANT_LABELS[it.variant],
                        "destination": it.view["destination"],
                        "days": it.view["days"],
                        "start_date": it.view["start_date"],
                        "total_price": it.total_price,
                        "budget": it.budget_total,
                        "hotel": it.view["hotel"]["name"],
                        "stars": it.view["hotel"]["stars"],
                        "top_activities": [d["activity"]["name"] for d in it.view["days_plan"]][:3],
                    }
                    for it in saved
                ],
            },
        )
        self._add_message(conv, "assistant", result.text, result=result, itinerary_ids=[it.id for it in saved])

    def _suggest(
        self, conv: Conversation, req: TripRequirements, start_dates: list[date]
    ) -> tuple[TripRequirements, list[str], str] | None:
        """ "Consigliami tu": code finds the feasible countries, the LLM picks one of them."""
        all_codes = sorted(self.session.scalars(select(Country.code)))
        catalogs = self._load(all_codes, req, start_dates)
        request = self._planning_request(req, start_dates, [], scored=False)
        costs = {c.code: minimum_cost(request, c) for c in catalogs}
        feasible = [c for c in catalogs if costs[c.code] is not None and costs[c.code] <= req.budget_total]  # type: ignore[operator]
        if not feasible:
            self._infeasible(conv, req, None, all_codes, start_dates)
            return None
        feasible_codes = [c.code for c in feasible]
        scores = self._scores(req, feasible_codes)
        rows = self.session.execute(
            select(Activity.id, Activity.country_code).where(Activity.country_code.in_(feasible_codes))
        )
        activity_country = {aid: code for aid, code in rows}
        countries = {c.code: c for c in self.session.scalars(select(Country).where(Country.code.in_(feasible_codes)))}
        options = []
        for c in feasible:
            top = sorted((s for aid, s in scores.items() if activity_country.get(aid) == c.code), reverse=True)[:5]
            options.append(
                {
                    "code": c.code,
                    "name": countries[c.code].name,
                    "destination": countries[c.code].destination,
                    "description": countries[c.code].description,
                    "min_cost": costs[c.code],
                    "preference_score": round(sum(top) / len(top), 3) if top else 0.0,
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
            budget = req.budget_total or 0
            if lowest is None:
                reason = "non ci sono abbastanza disponibilità (voli, hotel o attività) nelle date richieste."
            elif lowest > budget:
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
        budget = req.budget_total
        found: list[str] = []

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
            if cost is not None and cost <= budget:
                found.append(f"ridurre la durata a {days} giorni (da circa {cost} €)")
                break
        months = 0
        for offset in RELAXATION_MONTH_OFFSETS:
            month = (req.month - 1 + offset) % 12 + 1
            dates = trip_start_dates(resolve_month(self.session, month, self.today), req.duration.max_days)
            if not dates:
                continue
            cost = cheapest(req.model_copy(update={"month": month}), dates, codes)
            if cost is not None and cost <= budget:
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
                if cost is not None and cost <= budget:
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

    def _planning_request(
        self, req: TripRequirements, start_dates: list[date], codes: list[str], scored: bool = True
    ) -> PlanningRequest:
        assert req.budget_total and req.travelers and req.duration
        return PlanningRequest(
            budget=req.budget_total,
            travelers=req.travelers,
            start_dates=start_dates,
            min_days=req.duration.min_days,
            max_days=req.duration.max_days,
            activity_scores=self._scores(req, codes) if scored and codes else {},
        )

    def _scores(self, req: TripRequirements, codes: list[str]) -> dict[str, float]:
        assert req.preferences and req.month
        activities = list(self.session.scalars(select(Activity).where(Activity.country_code.in_(codes))))
        index = self.index_factory(activities)
        with self.tracer.observation(
            "rag.score_activities",
            as_type="retriever",
            input={"preferences": req.preferences.model_dump(), "countries": codes, "month": req.month},
        ) as span:
            scores = score_activities(index, req.preferences, activities, codes, req.month)
            names = {a.id: a.name for a in activities}
            top = sorted(scores.items(), key=lambda kv: -kv[1])[:5]
            span.update(output=[{"activity": names[aid], "score": score} for aid, score in top])
        return scores

    def _load(self, codes: list[str], req: TripRequirements, start_dates: list[date]) -> list[CountryCatalog]:
        assert req.departure_airport and req.duration
        date_to = start_dates[-1] + timedelta(days=req.duration.max_days)
        return load_catalogs(self.session, codes, req.departure_airport, start_dates[0], date_to)

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
