"""Trip requirements collected through the conversation (ADR-0002).

Every field is required and starts as ``None``: the conversation stays in the collection phase until
all of them are set. Some fields accept flexible values (destination ``suggest``/``anywhere``, a
duration range, month-only dates).
"""

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

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

MIN_DAYS = 2


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


class Preferences(BaseModel):
    categories: list[str] = Field(min_length=1)
    notes: str | None = None

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


class TripRequirements(BaseModel):
    budget_total: int | None = Field(default=None, gt=0)
    destination: Destination | None = None
    preferences: Preferences | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    duration: DurationRange | None = None
    departure_airport: str | None = None
    travelers: int | None = Field(default=None, ge=1, le=9)

    def missing_fields(self) -> list[str]:
        return [name for name in FIELD_LABELS if getattr(self, name) is None]

    def is_complete(self) -> bool:
        return not self.missing_fields()

    def merge(self, update: "RequirementsUpdate") -> "TripRequirements":
        """Apply a partial update: fields present in the update overwrite the current ones."""
        data = self.model_dump()
        for name, value in update.model_dump(exclude_none=True).items():
            if name == "preferences" and data.get("preferences") and value.get("notes") is None:
                value["notes"] = data["preferences"].get("notes")
            data[name] = value
        return TripRequirements.model_validate(data)


class RequirementsUpdate(BaseModel):
    """Partial update produced by the interpreter (LLM or mock) from a user message."""

    budget_total: int | None = Field(default=None, gt=0)
    destination: Destination | None = None
    preferences: Preferences | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    duration: DurationRange | None = None
    departure_airport: str | None = None
    travelers: int | None = Field(default=None, ge=1, le=9)

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
    if req.departure_airport and req.departure_airport.upper() not in facts.departure_airports:
        issues.append("Possiamo partire solo da Roma Fiumicino, Milano Malpensa o Napoli.")
        data["departure_airport"] = None
    elif req.departure_airport:
        data["departure_airport"] = req.departure_airport.upper()
    if req.duration and req.duration.max_days > facts.max_days:
        issues.append(f"La durata massima pianificabile è di {facts.max_days} giorni.")
        data["duration"] = None
    return TripRequirements.model_validate(data), issues
