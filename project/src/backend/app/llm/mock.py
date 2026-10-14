"""Deterministic rule-based provider: last link of the fallback chain (ADR-0005).

It answers every task without any network call: regex/keyword extraction for Italian and template
replies. It is also what tests and CI use, and the baseline for evals (ADR-0008): an LLM that cannot
beat these rules is not worth its cost.
"""

import re
import time

from pydantic import ValidationError

from app.domain.requirements import (
    MONTHS_IT,
    DestinationType,
    RequirementsUpdate,
)
from app.llm.base import LLMError, LLMResult, LLMTask, ToolCall
from app.llm.interpreter import DestinationChoice, Extraction, ProposalAction
from app.textfmt import day_it, eur

NUMBER_WORDS = {
    "un": 1,
    "uno": 1,
    "una": 1,
    "due": 2,
    "tre": 3,
    "quattro": 4,
    "cinque": 5,
    "sei": 6,
    "sette": 7,
    "otto": 8,
    "nove": 9,
    "dieci": 10,
    "undici": 11,
    "dodici": 12,
    "tredici": 13,
    "quattordici": 14,
}
_NUM = r"(\d+|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")"

COUNTRY_WORDS = {
    "IT": ["italia", "sicilia", "palermo", "catania"],
    "ES": ["spagna", "barcellona"],
    "GR": ["grecia", "atene"],
    "JP": ["giappone", "tokyo", "kyoto"],
    "IS": ["islanda", "reykjavik"],
    # Not in the catalog: recognised so the validator can say so instead of ignoring them.
    "FR": ["francia", "parigi"],
    "PT": ["portogallo", "lisbona"],
    "US": ["stati uniti", "new york", "usa"],
    "TH": ["thailandia"],
    "EG": ["egitto"],
    "MA": ["marocco"],
    "HR": ["croazia"],
    "GB": ["londra", "inghilterra"],
}
SUGGEST_PATTERNS = [r"consigli", r"suggeris", r"scegli tu", r"decidi tu", r"proponi tu", r"sorprendimi", r"non so dove"]
ANYWHERE_PATTERNS = [
    r"ovunque",
    r"qualsiasi (posto|meta|destinazione|paese|luogo)",
    r"dove vuoi",
    r"indifferente",
    r"un posto qualsiasi",
]
DEPARTURE_CITIES = {
    "FCO": ["roma", "fiumicino", "fco"],
    "MXP": ["milano", "malpensa", "mxp"],
    "NAP": ["napoli", "capodichino"],
    # Not served: recognised so the validator can say so.
    "BLQ": ["bologna"],
    "TRN": ["torino"],
    "VCE": ["venezia"],
    "BRI": ["bari"],
    "CTA": ["catania"],
}
CATEGORY_STEMS = {
    "cultura": ["cultur", "muse", "storia", "storic", "arte", "monument", "archeolog", "templ", "chies", "architett"],
    "sport": [
        "sport",
        "surf",
        "bici",
        "cicl",
        "sciare",
        "sci",
        "immersion",
        "snorkel",
        "kayak",
        "arrampic",
        "attività fisica",
    ],
    "relax": ["relax", "rilass", "spa", "terme", "termal", "benessere", "spiagg", "mare", "tranquill", "onsen"],
    "nightlife": [
        "nightlife",
        "vita notturna",
        "discotec",
        "locali",
        "feste",
        "party",
        "movida",
        "aperitiv",
        "ballare",
        "serata",
        "serate",
    ],
    "natura": [
        "natur",
        "escursion",
        "trekking",
        "parco",
        "parchi",
        "vulcan",
        "montagn",
        "cascat",
        "ghiacc",
        "panoram",
        "passeggiat",
    ],
    "gastronomia": [
        "cibo",
        "gastronom",
        "cucina",
        "vino",
        "vini",
        "degust",
        "street food",
        "mangiare",
        "ristorant",
        "sushi",
        "tapas",
        "food",
    ],
}
ALL_CATEGORIES_PATTERNS = [r"un po' di tutto", r"di tutto", r"qualsiasi attivit", r"tutte le attivit"]
CHANGE_INTENT = r"preferi|invece|piuttosto|meglio|cambi|vorrei|più |di più|meno "
VARIANT_WORDS = {
    "economy": ["econom", "low cost", "la prima", "prima opzione", "risparm"],
    "balanced": ["bilanciat", "equilibrat", "la seconda", "seconda opzione", "intermedi", "via di mezzo"],
    "premium": ["premium", "lusso", "la terza", "terza opzione", "la migliore", "più cara", "top"],
}


# Scope (ADR-0016): a message is in scope if it carries a travel requirement, mentions travel topics or
# the catalog, or is a short greeting/acknowledgement. Everything else is refused.
TRAVEL_STEMS = [
    "viagg",
    "vacanz",
    "volo",
    "voli",
    "aere",
    "hotel",
    "albergh",
    "alloggi",
    "dormire",
    "camer",
    "meta",
    "destinaz",
    "itinerar",
    "attivit",
    "prenot",
    "budget",
    "costo",
    "costa",
    "prezz",
    "spes",
    "partenz",
    "partire",
    "parto",
    "partiamo",
    "ritorno",
    "soggiorn",
    "gita",
    "gite",
    "tour",
    "visit",
    "giorn",
    "nott",
    "settiman",
    "biglietto",
    "valigia",
    "clima",
    "tempo fa",
    "variant",
    "proposta",
    "opzion",
    "cancell",
    "annull",
    "pacchetto",
    "spiagg",
    "isol",
    "citt",
    "paese",
    "luogh",
    "posto",
]
ACK_PATTERN = (
    r"(ciao|salve|buongiorno|buonasera|hey|grazie( mille)?|ok|okay|va bene|perfetto|s[iì]|no|certo|"
    r"d'accordo|bene|ottimo|aiuto|help)[\s!.,?]*"
)


# Requests that are out of scope whatever travel words they contain ("scrivimi una poesia sul mare").
OFF_TOPIC_PATTERN = (
    r"\b(scriv\w*|componi|inventa)\w* (mi )?(una |un |del |dei |delle )?(poesi|raccont|stori|codic|tem[ai]\b|"
    r"canzon|email|mail|letter|articol|barzellett)|\btradu\w*|\brisolv\w*|\bcalcol\w*|\bprogramm\w*|"
    r"\bcodice (python|java|sql)|\bricett\w*|\bcompiti\b|\bbarzellett\w*|\bprompt\b|\bistruzioni\b|"
    r"\bjailbreak|\bfingi di essere|\bfai finta di essere"
)


def is_off_topic_request(text: str) -> bool:
    return re.search(OFF_TOPIC_PATTERN, text.lower()) is not None


def is_in_scope(text: str, update: RequirementsUpdate | None = None) -> bool:
    text = text.lower().strip()
    if is_off_topic_request(text):
        return False
    if update is not None and not update.is_empty():
        return True
    if re.fullmatch(ACK_PATTERN, text) or re.fullmatch(r"[\s\d.,!?]*", text):
        return True
    stems = TRAVEL_STEMS + [w for words in COUNTRY_WORDS.values() for w in words]
    stems += [w for words in DEPARTURE_CITIES.values() for w in words] + MONTHS_IT
    stems += [s for words in CATEGORY_STEMS.values() for s in words]
    stems += [w for words in VARIANT_WORDS.values() for w in words]
    return any(re.search(rf"\b{re.escape(s)}", text) for s in stems)


def _to_int(token: str) -> int:
    return int(token) if token.isdigit() else NUMBER_WORDS[token]


def _last_match(patterns: dict[str, list[str]], text: str, prefix: bool = False) -> str | None:
    """Key whose pattern appears last in the text: in "non luglio, anzi agosto" agosto wins.
    With ``prefix`` the words are stems ("bilanciat" matches "bilanciata")."""
    best, best_pos = None, -1
    end = "" if prefix else r"\b"
    for key, words in patterns.items():
        for w in words:
            for m in re.finditer(rf"\b{re.escape(w)}{end}", text):
                if m.start() > best_pos:
                    best, best_pos = key, m.start()
    return best


def parse_budget(text: str) -> int | None:
    amount = r"(\d{1,3}(?:[.\s]\d{3})+|\d+(?:[.,]\d+)?)\s*(k|mila)?"
    patterns = [
        rf"{amount}\s*(?:€|euro|eur)\b",
        rf"€\s*{amount}",
        rf"budget\D{{0,15}}{amount}",
        rf"spendere\D{{0,15}}{amount}",
        rf"{amount}\s*(?:k|mila)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            raw, multiplier = m.group(1), m.group(2)
            if re.fullmatch(r"\d{1,3}(?:[.\s]\d{3})+", raw):
                value = float(re.sub(r"[.\s]", "", raw))
            else:
                value = float(raw.replace(",", "."))
            if multiplier:
                value *= 1000
            return round(value) if value > 0 else None
    return None


def parse_duration(text: str) -> tuple[int, int] | None:
    unit = r"(giorni|giorno|gg|notti|notte)"
    m = re.search(rf"(?:da|tra|fra)\s+{_NUM}\s*(?:a|e|-)\s*{_NUM}\s*{unit}", text) or re.search(
        rf"{_NUM}\s*-\s*{_NUM}\s*{unit}", text
    )
    if m:
        lo, hi, u = _to_int(m.group(1)), _to_int(m.group(2)), m.group(3)
        extra = 1 if u.startswith("nott") else 0
        return lo + extra, hi + extra
    m = re.search(rf"{_NUM}\s*{unit}", text)
    if m:
        n, u = _to_int(m.group(1)), m.group(2)
        n += 1 if u.startswith("nott") else 0
        return n, n
    if re.search(r"due settimane|un paio di settimane", text):
        return 14, 14
    if re.search(r"una settimana|\bsettimana\b", text):
        return 7, 7
    if re.search(r"weekend|fine settimana", text):
        return 3, 3
    return None


def parse_travelers(text: str) -> int | None:
    m = re.search(rf"{_NUM}\s*(persone|viaggiatori|adulti|pax)", text) or re.search(rf"siamo (?:in )?{_NUM}", text)
    if m:
        return _to_int(m.group(1))
    m = re.search(rf"con {_NUM} amic", text)
    if m:
        return _to_int(m.group(1)) + 1
    if re.search(r"da sol[oa]|solo io|viaggio sol[oa]", text):
        return 1
    couple = (
        r"in due(?!\s*(?:settiman|giorn|nott|mes))|in coppia|io e (mia|mio|la mia|il mio)|"
        r"con (mia moglie|mio marito|la mia ragazza|il mio ragazzo|il mio compagno|la mia compagna|"
        r"il mio partner|la mia partner)"
    )
    if re.search(couple, text):
        return 2
    m = re.search(rf"\bin {_NUM}\b(?!\s*(?:giorn|nott|settiman|mes|ore))", text)
    if m and m.group(1) not in ("un", "una", "uno"):
        return _to_int(m.group(1))
    return None


def parse_departure(text: str, departure_missing: bool) -> str | None:
    for code, cities in DEPARTURE_CITIES.items():
        for city in cities:
            if re.search(rf"(?:da|parto da|partenza:?(?: da)?|partendo da|partiamo da)\s+{city}\b", text):
                return code
    if departure_missing:
        stripped = re.sub(r"[^a-z ]", "", text).strip()
        for code, cities in DEPARTURE_CITIES.items():
            if stripped in cities:
                return code
    return None


def parse_destination(text: str) -> dict | None:
    if any(re.search(p, text) for p in SUGGEST_PATTERNS):
        return {"type": DestinationType.SUGGEST}
    if any(re.search(p, text) for p in ANYWHERE_PATTERNS):
        return {"type": DestinationType.ANYWHERE}
    # Departure cities must not be read as destinations ("da Napoli").
    cleaned = re.sub(r"(?:da|parto da|partenza da|partendo da|partiamo da)\s+\w+", " ", text)
    code = _last_match(COUNTRY_WORDS, cleaned)
    return {"type": DestinationType.COUNTRY, "country_code": code} if code else None


def parse_month(text: str) -> int | None:
    found = _last_match({str(i + 1): [m] for i, m in enumerate(MONTHS_IT)}, text)
    return int(found) if found else None


def parse_preferences(text: str, original: str) -> dict | None:
    if any(re.search(p, text) for p in ALL_CATEGORIES_PATTERNS):
        categories = list(CATEGORY_STEMS)
    else:
        # Stems must start a word: "arte" must not match "partenza".
        categories = [c for c, stems in CATEGORY_STEMS.items() if any(re.search(rf"\b{s}", text) for s in stems)]
    if not categories:
        return None
    return {"categories": categories, "notes": original.strip()[:300]}


def extract(message: str, missing: list[str]) -> RequirementsUpdate:
    text = message.lower()
    data: dict = {}
    if (budget := parse_budget(text)) is not None:
        data["budget_total"] = budget
    if (duration := parse_duration(text)) is not None:
        data["duration"] = {"min_days": duration[0], "max_days": duration[1]}
    if (travelers := parse_travelers(text)) is not None:
        data["travelers"] = travelers
    if (departure := parse_departure(text, "departure_airport" in missing)) is not None:
        data["departure_airport"] = departure
    if (destination := parse_destination(text)) is not None:
        data["destination"] = destination
    if (month := parse_month(text)) is not None:
        data["month"] = month
    if (preferences := parse_preferences(text, message)) is not None:
        data["preferences"] = preferences
    # A bare number answers the pending numeric question (e.g. "1500" after "quanto vuoi spendere?").
    bare = re.fullmatch(r"\s*(\d+)\s*", text)
    if bare:
        n = int(bare.group(1))
        if "budget_total" in missing and n >= 100:
            data.setdefault("budget_total", n)
        elif "travelers" in missing and 1 <= n <= 9:
            data.setdefault("travelers", n)
    try:
        return RequirementsUpdate.model_validate(data)
    except ValidationError:
        # Keep whatever is individually valid.
        valid = {}
        for key, value in data.items():
            try:
                RequirementsUpdate.model_validate({key: value})
                valid[key] = value
            except ValidationError:
                continue
        return RequirementsUpdate.model_validate(valid)


def interpret_proposal(message: str, variants: list[str]) -> ProposalAction:
    text = message.lower()
    if is_off_topic_request(text):
        return ProposalAction(action="out_of_scope")
    variant = _last_match({v: words for v, words in VARIANT_WORDS.items() if v in variants}, text, prefix=True)
    if variant:
        return ProposalAction(action="select_variant", variant=variant)
    update = extract(message, [])
    # While looking at proposals, "quanto costa il museo?" is a question, not a new preference: keep
    # preference changes only when the user clearly asks for a change.
    if update.preferences is not None and not re.search(CHANGE_INTENT, text):
        update = update.model_copy(update={"preferences": None})
    if not update.is_empty():
        return ProposalAction(action="update_requirements", requirements=update)
    if not is_in_scope(text):
        return ProposalAction(action="out_of_scope")
    return ProposalAction(action="question")


SWAP_PATTERN = r"\bgiorno\s+(\d{1,2})\b|\b(\d{1,2})[°º]?\s*giorno\b"
CHANGE_WORDS = r"cambi|sostitu|vorrei|preferi|altr[oa]|divers|invece|più |meno "
HOTEL_BETTER = r"miglior|più bello|più stelle|superiore|lusso|più confortevole"
HOTEL_CHEAPER = r"econom|meno car|risparm|più basso|costa meno"
SEARCH_PATTERN = r"(che|quali) attivit|cosa (c'è|ce|si può|posso) fare|attività (ci sono|disponibili)|cosa offre"


def choose_tool(message: str, proposals: list[dict], phase: str) -> tuple[str, dict] | None:
    """Rule-based emulation of the proposal-phase tool choice; ``None`` means a plain text answer."""
    text = message.lower()
    variants = [p["variant"] for p in proposals]
    mentioned = _last_match({v: w for v, w in VARIANT_WORDS.items() if v in variants}, text, prefix=True)
    chosen = next((p["variant"] for p in proposals if p.get("stato") == "scelta"), None)
    target = mentioned or chosen or ("balanced" if "balanced" in variants else (variants[0] if variants else None))
    if is_off_topic_request(text):
        return "flag_out_of_scope", {}
    day = re.search(SWAP_PATTERN, text)
    if day and target and re.search(CHANGE_WORDS, text):
        found = parse_preferences(text, message)
        category = found["categories"][0] if found and len(found["categories"]) == 1 else "qualsiasi"
        return "swap_activity", {
            "variant": target,
            "day": int(day.group(1) or day.group(2)),
            "request": message,
            "category": category,
        }
    if re.search(r"\b(hotel|albergo)", text) and target:
        if re.search(HOTEL_BETTER, text):
            return "change_hotel", {"variant": target, "direction": "better"}
        if re.search(HOTEL_CHEAPER, text):
            return "change_hotel", {"variant": target, "direction": "cheaper"}
    if re.search(SEARCH_PATTERN, text):
        return "search_activities", {"query": message}
    action = interpret_proposal(message, variants)
    if action.action == "select_variant":
        return "select_variant", {"variant": action.variant}
    if action.action == "update_requirements":
        return "update_requirements", {"change": message}
    if action.action == "out_of_scope":
        return "flag_out_of_scope", {}
    return None


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " e " + items[-1]


FIELD_QUESTIONS = {
    "budget_total": "quanto vuoi spendere in totale",
    "destination": "dove vorresti andare (Sicilia, Spagna, Grecia, Giappone o Islanda; oppure «consigliami tu» "
    "o «ovunque»)",
    "preferences": "che attività ti piacciono (cultura, sport, relax, nightlife, natura, gastronomia)",
    "month": "in che mese vuoi partire",
    "duration": "quanti giorni (va bene anche un intervallo, es. 5-7 giorni)",
    "departure_airport": "da dove parti (Roma Fiumicino, Milano Malpensa o Napoli)",
    "travelers": "quante persone viaggiano",
}
VARIANT_LABELS = {"economy": "Economica", "balanced": "Bilanciata", "premium": "Premium"}


def write_reply(kind: str, facts: dict) -> str:
    if kind == "ask_missing":
        parts = list(facts.get("issues", []))
        questions = [FIELD_QUESTIONS[f] for f in facts["missing_fields"][:3]]
        if questions:
            ask = f"Per preparare l'itinerario dimmi {_join(questions)}."
            parts.append(ask if not facts.get("known") else f"Perfetto, ho preso nota. {ask}")
        return " ".join(parts)
    if kind == "present_itineraries":
        lines = []
        if facts.get("destination_reason"):
            lines.append(facts["destination_reason"])
        lines.append("Ecco le proposte che rispettano budget e disponibilità:")
        for v in facts["variants"]:
            acts = ", ".join(v["top_activities"][:2])
            lines.append(
                f"- **{VARIANT_LABELS[v['variant']]}**: {v['destination']}, {v['days']} giorni "
                f"dal {day_it(v['start_date'])}, "
                f"hotel {v['hotel']} ({v['stars']}★), **{eur(v['total_price'])}** su {eur(v['budget'])}. "
                f"Tra le attività: {acts}."
            )
        lines.append("\nQuale preferisci? Puoi anche chiedermi di cambiare un requisito.")
        return "\n".join(lines)
    if kind == "infeasible":
        alternatives = facts.get("alternatives", [])
        text = f"Con questi requisiti non riesco a costruire un itinerario: {facts['reason']}"
        if alternatives:
            text += " Ecco cosa possiamo fare:\n\n" + "\n".join(f"- {a}" for a in alternatives)
            text += "\n\nDimmi quale preferisci (per esempio scrivendo il nuovo valore)."
        return text
    if kind == "confirm_summary":
        return (
            f"Ottima scelta: variante **{VARIANT_LABELS[facts['variant']]}**, {facts['destination']}, "
            f"{facts['days']} giorni dal {day_it(facts['start_date'])} al {day_it(facts['end_date'])} "
            f"per {facts['travelers']} "
            f"{'persona' if facts['travelers'] == 1 else 'persone'}, totale **{eur(facts['total_price'])}**. "
            "Per prenotare premi **Conferma e prenota**: la prenotazione parte solo con il tuo clic."
        )
    if kind == "answer":
        if facts.get("phase") == "AWAITING_CONFIRMATION":
            return (
                "Per sicurezza posso prenotare solo quando premi il pulsante «Conferma e prenota». "
                "Se preferisci un'altra variante o vuoi cambiare un requisito, dimmelo."
            )
        return (
            "Posso aiutarti a scegliere tra le varianti proposte: scrivi «economica», «bilanciata» o "
            "«premium», oppure chiedimi di cambiare un requisito (per esempio il mese o la durata)."
        )
    raise LLMError(f"mock: unknown reply kind {kind}")


class MockProvider:
    name = "MOCK"
    model = "rules-v1"

    def is_configured(self) -> bool:
        return True

    def __init__(self, stream_delay_ms: int = 0):
        self.stream_delay_ms = stream_delay_ms  # optional pacing so streaming is visible in demos

    def generate(self, task: LLMTask, on_token=None) -> LLMResult:
        started = time.perf_counter()
        ctx = task.context
        parsed = None
        text = ""
        if task.name == "extract_requirements":
            if is_off_topic_request(ctx["message"]):
                parsed = Extraction(in_scope=False)  # do not mine requirements out of an off-topic request
            else:
                update = extract(ctx["message"], ctx.get("missing", []))
                parsed = Extraction(in_scope=is_in_scope(ctx["message"], update), requirements=update)
        elif task.name == "choose_destination":
            best = max(ctx["feasible"], key=lambda c: (c["preference_score"], -c["min_cost"]))
            parsed = DestinationChoice(
                country_code=best["code"],
                reason=f"Ti consiglio {best['name']} ({best['destination']}): tra le mete che rientrano nel budget "
                "è quella con le attività più vicine ai tuoi gusti.",
            )
        elif task.name == "proposal_tools":
            if ctx["tool_summaries"]:  # second step: report what the tools did (code-written summaries)
                text = " ".join(ctx["tool_summaries"])
            else:
                choice = choose_tool(ctx["message"], ctx["proposals"], ctx["phase"])
                if choice is not None:
                    name, arguments = choice
                    return LLMResult(
                        text="",
                        parsed=None,
                        provider=self.name,
                        model=self.model,
                        input_tokens=0,
                        output_tokens=0,
                        tool_calls=[ToolCall(id=f"mock-{name}", name=name, arguments=arguments)],
                    )
                text = write_reply("answer", {"phase": ctx["phase"]})
        elif task.name.startswith("reply:"):
            text = write_reply(ctx["kind"], ctx)
        else:
            raise LLMError(f"mock: unknown task {task.name}")
        if parsed is not None:
            text = parsed.model_dump_json()
        elif on_token is not None:
            for word in re.findall(r"\S+\s*", text):
                on_token(word)
                if self.stream_delay_ms:
                    time.sleep(self.stream_delay_ms / 1000)
        return LLMResult(
            text=text,
            parsed=parsed,
            provider=self.name,
            model=self.model,
            input_tokens=0,
            output_tokens=0,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
