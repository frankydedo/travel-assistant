"""Conversation state machine (ADR-0001).

Transitions are decided by code from the structured state, never by the LLM text.
"""

import logging
from enum import StrEnum
from typing import Protocol

log = logging.getLogger(__name__)


class Phase(StrEnum):
    COLLECTING_REQUIREMENTS = "COLLECTING_REQUIREMENTS"
    PROPOSING = "PROPOSING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    BOOKED = "BOOKED"


ALLOWED_TRANSITIONS: dict[Phase, set[Phase]] = {
    Phase.COLLECTING_REQUIREMENTS: {Phase.COLLECTING_REQUIREMENTS, Phase.PROPOSING},
    Phase.PROPOSING: {Phase.PROPOSING, Phase.COLLECTING_REQUIREMENTS, Phase.AWAITING_CONFIRMATION},
    Phase.AWAITING_CONFIRMATION: {
        Phase.AWAITING_CONFIRMATION,
        Phase.PROPOSING,
        Phase.COLLECTING_REQUIREMENTS,
        Phase.BOOKED,
    },
    Phase.BOOKED: set(),
}


class InvalidTransition(Exception):
    pass


def transition(current: Phase | str, target: Phase) -> Phase:
    current = Phase(current)
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(f"{current} -> {target} is not allowed")
    return target


class HasPhase(Protocol):
    id: str
    phase: str


def change_phase(conversation: HasPhase, target: Phase) -> None:
    """Apply a validated transition and log it when the phase actually changes."""
    current = Phase(conversation.phase)
    conversation.phase = transition(current, target)
    if current != target:
        log.info(
            "conversation.phase_changed",
            extra={"from_phase": str(current), "to_phase": str(target), "conversation_id": conversation.id},
        )
