import pytest
from pydantic import ValidationError

from app.domain.phases import InvalidTransition, Phase, transition
from app.domain.requirements import (
    CatalogFacts,
    DestinationType,
    RequirementsUpdate,
    TripRequirements,
    validate_against_catalog,
)

FACTS = CatalogFacts(
    country_codes={"IT", "ES", "GR", "JP", "IS"}, departure_airports={"FCO", "MXP", "NAP"}, max_days=14
)


def test_all_fields_start_missing():
    assert TripRequirements().missing_fields() == [
        "budget_total",
        "destination",
        "preferences",
        "month",
        "duration",
        "departure_airport",
        "travelers",
    ]


def test_merge_overwrites_only_given_fields_and_keeps_notes():
    req = TripRequirements(month=7, preferences={"categories": ["relax"], "notes": "mare"})
    merged = req.merge(RequirementsUpdate(month=8, preferences={"categories": ["cultura"]}))
    assert merged.month == 8
    assert merged.preferences.categories == ["cultura"]
    assert merged.preferences.notes == "mare"


def test_flexible_values():
    req = TripRequirements(
        destination={"type": "suggest", "country_code": "IT"}, duration={"min_days": 7, "max_days": 5}
    )
    assert req.destination.type == DestinationType.SUGGEST and req.destination.country_code is None
    assert (req.duration.min_days, req.duration.max_days) == (5, 7)


def test_invalid_values_are_rejected():
    with pytest.raises(ValidationError):
        TripRequirements(budget_total=-10)
    with pytest.raises(ValidationError):
        TripRequirements(preferences={"categories": ["shopping"]})
    with pytest.raises(ValidationError):
        TripRequirements(destination={"type": "country"})


def test_catalog_validation_resets_unsatisfiable_fields():
    req = TripRequirements(
        destination={"type": "country", "country_code": "FR"},
        departure_airport="trn",
        duration={"min_days": 5, "max_days": 20},
    )
    cleaned, issues = validate_against_catalog(req, FACTS)
    assert cleaned.destination is None and cleaned.departure_airport is None and cleaned.duration is None
    assert len(issues) == 3


def test_phase_transitions():
    assert transition(Phase.COLLECTING_REQUIREMENTS, Phase.PROPOSING) == Phase.PROPOSING
    assert transition(Phase.AWAITING_CONFIRMATION, Phase.BOOKED) == Phase.BOOKED
    with pytest.raises(InvalidTransition):
        transition(Phase.COLLECTING_REQUIREMENTS, Phase.BOOKED)  # booking needs a confirmed proposal
    with pytest.raises(InvalidTransition):
        transition(Phase.BOOKED, Phase.AWAITING_CONFIRMATION)  # a cancellation reopens, never re-confirms
    assert transition(Phase.BOOKED, Phase.PROPOSING) == Phase.PROPOSING  # ADR-0024: cancelled booking
