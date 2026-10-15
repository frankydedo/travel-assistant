"""Trip requirements collected through the conversation (ADR-0002).

Every field is required and starts as ``None``: the conversation stays in the collection phase until
all of them are set. Some fields accept flexible values (destination ``suggest``/``anywhere``, a
duration range, month-only dates).
"""

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

CATEGORIES: dict[str, str] = {
    "cultura": "Cultura",
    "sport": "Sport",
    "relax": "Relax",
    "nightlife": "Nightlife",
    "natura": "Natura",
    "gastronomia": "Gastronomia",
}

FIELD_LABELS: dict[str, str] = {
    "budget_total": "budget totale",
    "destination": "destinazione",
    "preferences": "preferenze sulle attività",
    "month": "mese del viaggio",
    "duration": "durata",
    "departure_airport": "aeroporto di partenza",
    "travelers": "numero di viaggiatori",
}

MONTHS_IT = [
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
]

# Dates are month-only (ADR-0002): a specific day ("il 4 febbraio", "10/03") is detected by code so the
# reply can say so instead of silently dropping it.
_EXACT_DATE = re.compile(
    r"\b(?:[1-9]|[12]\d|3[01])\s*[°º]?\s+(?:" + "|".join(MONTHS_IT) + r")\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",
    re.IGNORECASE,
)


def mentions_exact_date(text: str) -> bool:
    return _EXACT_DATE.search(text) is not None


MIN_DAYS = 2
MAX_TRAVELERS = 9

# Explicit "any" values (ADR-0021). They are values the user states, never defaults: a field nobody
# talked about stays null, and code accepts these values only with an explicit expression in the
# user's own message (``keep_explicit_any``).
UNLIMITED_BUDGET = "unlimited"
ANY_AIRPORT = "ANY"

UNLIMITED_BUDGET_PATTERN = (
    r"illimitat|budget (libero|aperto|infinito)|senza (limit\w* di )?(budget|spesa)|senza limiti di spesa|"
    r"nessun (limite|tetto)|non (ho|abbiamo|c'è) (un |alcun |nessun )?(limite|tetto|budget)|"
    r"(i )?soldi non (sono|è) un problema|non (mi |ci )?importa (il prezzo|quanto (costa|si spende|spend))"
)
ANY_AIRPORT_PATTERN = (
    r"(qualsiasi|qualunque) aeroporto|aeroporto (indifferente|qualsiasi|qualunque)|"
    r"partenza (indifferente|libera|da qualsiasi|da qualunque)|"
    r"(parto|partiamo|partire|partenza) da (qualsiasi|qualunque|ovunque|dove (vuoi|conviene|costa meno))|"
    r"(da )?(qualsiasi|qualunque) città|non (mi |ci )?importa da dove|da tutti e tre"
)
NO_PREFERENCES_PATTERN = (
    r"nessuna preferenza|non (ho|abbiamo) (particolari |nessuna )?preferenz|senza preferenz|"
    r"(mi|ci) va bene (qualsiasi cosa|tutto)|attività indifferent|non (mi|ci) interessa (cosa|il tipo)|"
    r"nessun interesse (particolare|specifico)"
)
# A bare "any" answer ("indifferente", "fa lo stesso") counts only when that field is the one still missing.
GENERIC_ANY_PATTERN = r"^\W*(indifferente|qualsiasi|qualunque|fa lo stesso|è uguale|non importa|va bene tutto)\W*$"


class DestinationType(StrEnum):
    COUNTRY = "country"
    SUGGEST = "suggest"  # "consigliami tu": the LLM picks among feasible countries
    ANYWHERE = "anywhere"  # no country filter: the planner evaluates every destination


class Destination(BaseModel):
    type: DestinationType
    country_code: str | None = None

    @model_validator(mode="after")
    def _country_code_matches_type(self) -> "Destination":
        if self.type == DestinationType.COUNTRY and not self.country_code:
            raise ValueError("country_code is required when type is 'country'")
        if self.type != DestinationType.COUNTRY:
            self.country_code = None
        if self.country_code:
            self.country_code = self.country_code.upper()
        return self


NOTES_MAX_LENGTH = 200
NOTES_DESCRIPTION = (
    "I gusti dell'utente in poche parole e con le sue parole, per la ricerca semantica delle attività "
    "(es. 'mare e vita notturna', 'posti tranquilli, niente folla', 'con bambini piccoli'). Includi per chi è "
    "il viaggio (bambini, anziani, coppia) se l'utente lo dice: le attività hanno un pubblico di riferimento. "
    "Niente budget, date, durata, destinazione, partenza o numero di persone: hanno già il loro campo. "
    "null se l'utente non descrive gusti."
)

# Fragments of the notes that repeat a structured requirement: they would only add noise to the RAG query.
_STRUCTURED_FRAGMENT = re.compile(
    r"\d+\s*(€|euro|eur\b|k\b|mila)|€\s*\d|\bbudget|\bspend|\bpersone|\bsiamo\b|\bviaggiator|\bda sol[oa]\b|"
    r"\bin (due|tre|quattro|\d)\b|\bgiorn|\bnott[ei]\b|\bsettiman|\bweekend|\bpart(o|iamo|enza|ire)\b|"
    r"\baeroport|\bda (roma|milano|napoli)\b|\b(" + "|".join(MONTHS_IT) + r")\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[a-zà-ù']{4,}", re.IGNORECASE)


def clean_preference_notes(notes: str | None, message: str | None = None) -> str | None:
    """Keep only the tastes. Notes only rank activities (they never change constraints), so a bad note is
    cleaned, never rejected: rejecting would cost a retry, or the whole extraction, for a soft field.

    With the user's message as validation context, a note whose words are mostly absent from it is
    dropped: the interpreter may paraphrase, not invent tastes."""
    if not notes:
        return None
    fragments = [f.strip() for f in re.split(r"[,.;:!?\n]+", notes)]
    kept = ", ".join(f for f in fragments if f and not _STRUCTURED_FRAGMENT.search(f))[:NOTES_MAX_LENGTH]
    if not kept:
        return None
    if message:
        words = [w.lower() for w in _WORD.findall(kept)]
        said = message.lower()
        grounded = sum(1 for w in words if w[:5] in said)  # 5-letter stems tolerate "spiagge"/"spiaggia"
        if words and grounded * 2 < len(words):
            return None
    return kept


class Preferences(BaseModel):
    categories: list[str]  # [] = the user explicitly has no preference (ADR-0021)
    notes: str | None = Field(default=None, max_length=NOTES_MAX_LENGTH, description=NOTES_DESCRIPTION)

    @field_validator("notes", mode="before")
    @classmethod
    def _not_too_long(cls, value):
        # A long note is cut, not rejected: rejecting would fail the whole extraction for a soft field.
        return value[:NOTES_MAX_LENGTH] if isinstance(value, str) else value

    @field_validator("notes", mode="after")
    @classmethod
    def _only_tastes(cls, value: str | None, info: ValidationInfo) -> str | None:
        message = (info.context or {}).get("message")
        return clean_preference_notes(value, message)

    @property
    def none(self) -> bool:
        return not self.categories

    @field_validator("categories")
    @classmethod
    def _known_categories(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(c.lower().strip() for c in value))
        unknown = [c for c in cleaned if c not in CATEGORIES]
        if unknown:
            raise ValueError(f"unknown categories: {unknown}")
        return cleaned


class DurationRange(BaseModel):
    min_days: int = Field(ge=MIN_DAYS)
    max_days: int = Field(ge=MIN_DAYS)

    @model_validator(mode="after")
    def _ordered(self) -> "DurationRange":
        if self.min_days > self.max_days:
            self.min_days, self.max_days = self.max_days, self.min_days
        return self


Budget = int | Literal["unlimited"]


def _check_budget(value):
    if isinstance(value, int) and value <= 0:
        raise ValueError("budget must be positive")
    return value


class TripRequirements(BaseModel):
    budget_total: Budget | None = None
    destination: Destination | None = None
    preferences: Preferences | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    duration: DurationRange | None = None
    departure_airport: str | None = None
    travelers: int | None = Field(default=None, ge=1)  # upper bound checked by validate_against_catalog

    _budget = field_validator("budget_total")(classmethod(lambda cls, v: _check_budget(v)))

    @property
    def budget_limit(self) -> int | None:
        """The budget as a number; None when it is unlimited (or not given yet)."""
        return self.budget_total if isinstance(self.budget_total, int) else None

    @property
    def any_airport(self) -> bool:
        return self.departure_airport == ANY_AIRPORT

    def missing_fields(self) -> list[str]:
        return [name for name in FIELD_LABELS if getattr(self, name) is None]

    def is_complete(self) -> bool:
        return not self.missing_fields()

    def merge(self, update: "RequirementsUpdate") -> "TripRequirements":
        """Apply a partial update: fields present in the update overwrite the current ones."""
        data = self.model_dump()
        for name, value in update.model_dump(exclude_none=True).items():
            if (
                name == "preferences"
                and data.get("preferences")
                and value.get("notes") is None
                and value.get("categories")
            ):
                value["notes"] = data["preferences"].get("notes")
            data[name] = value
        return TripRequirements.model_validate(data)


class RequirementsUpdate(BaseModel):
    """Partial update produced by the interpreter (LLM or mock) from a user message."""

    budget_total: Budget | None = None
    destination: Destination | None = None
    preferences: Preferences | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    duration: DurationRange | None = None
    departure_airport: str | None = None
    travelers: int | None = Field(default=None, ge=1)  # upper bound checked by validate_against_catalog

    _budget = field_validator("budget_total")(classmethod(lambda cls, v: _check_budget(v)))

    def is_empty(self) -> bool:
        return not self.model_dump(exclude_none=True)


class CatalogFacts(BaseModel):
    """What the validator needs to know about the catalog."""

    country_codes: set[str]
    departure_airports: set[str]
    max_days: int


def validate_against_catalog(req: TripRequirements, facts: CatalogFacts) -> tuple[TripRequirements, list[str]]:
    """Reset fields that the catalog cannot satisfy and return user-facing issues (Italian)."""
    issues: list[str] = []
    data = req.model_dump()
    if req.destination and req.destination.type == DestinationType.COUNTRY:
        if req.destination.country_code not in facts.country_codes:
            issues.append("Al momento non abbiamo offerte per quella destinazione.")
            data["destination"] = None
    if req.departure_airport and req.departure_airport.upper() == ANY_AIRPORT:
        data["departure_airport"] = ANY_AIRPORT
    elif req.departure_airport and req.departure_airport.upper() not in facts.departure_airports:
        issues.append("Possiamo partire solo da Roma Fiumicino, Milano Malpensa o Napoli.")
        data["departure_airport"] = None
    elif req.departure_airport:
        data["departure_airport"] = req.departure_airport.upper()
    if req.travelers and req.travelers > MAX_TRAVELERS:
        # Said to the user instead of being dropped by schema validation (a group of 15 is not "no answer").
        issues.append(f"Possiamo organizzare viaggi per al massimo {MAX_TRAVELERS} persone.")
        data["travelers"] = None
    if req.duration and req.duration.max_days > facts.max_days:
        issues.append(f"La durata massima pianificabile è di {facts.max_days} giorni.")
        data["duration"] = None
    return TripRequirements.model_validate(data), issues


def keep_explicit_any(update: RequirementsUpdate, message: str, missing: list[str]) -> RequirementsUpdate:
    """Drop "any" values the user did not state (ADR-0021): an interpreter that fills a gap with "any"
    would be a silent default. The check runs on the user's own message, never on the LLM's paraphrase."""
    text = message.lower()
    generic = re.search(GENERIC_ANY_PATTERN, text) is not None

    def stated(pattern: str, field: str) -> bool:
        return re.search(pattern, text) is not None or (generic and missing == [field])

    changes: dict = {}
    if update.budget_total == UNLIMITED_BUDGET and not stated(UNLIMITED_BUDGET_PATTERN, "budget_total"):
        changes["budget_total"] = None
    if update.departure_airport and update.departure_airport.upper() == ANY_AIRPORT:
        if not stated(ANY_AIRPORT_PATTERN, "departure_airport"):
            changes["departure_airport"] = None
    if update.preferences is not None and update.preferences.none:
        if not stated(NO_PREFERENCES_PATTERN, "preferences"):
            changes["preferences"] = None
    return update.model_copy(update=changes) if changes else update
