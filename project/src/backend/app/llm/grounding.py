"""Deterministic checks on the text an LLM writes (ADR-0025).

The prompt says "use only the facts you are given", and models still change numbers (1963 € became
"1 966 €" in a real conversation). Every euro amount in a reply must therefore be one of the amounts the
code gave the model, or the difference between two of them ("24 € in più"). A reply that fails is
replaced by the text written by code: a wrong price must never reach the user, even if the cards are right.

Only amounts count as known numbers (numeric values in the facts and euro amounts inside their strings):
dates and years are not, otherwise "2026 - 60" would vouch for an invented 1966 €.
"""

import json
import re
from itertools import combinations
from typing import Any

# Thousands separators: dot, comma before exactly three digits, a (narrow) no-break space or one space.
_THOUSANDS = r"\d{1,3}(?:(?:[.,  ]| (?=\d{3}\b))\d{3})+"
_NUMBER = rf"({_THOUSANDS}|\d+)(?:,\d{{1,2}})?"
_AMOUNT = re.compile(rf"(?:€\s?{_NUMBER})|(?:\b{_NUMBER}\s?(?:€|euro\b|eur\b))", re.IGNORECASE)


def _to_int(raw: str) -> int:
    return int(re.sub(r"[.,   ]", "", raw))


def _matches(text: str) -> list[str]:
    return [a or b for a, b in _AMOUNT.findall(text)]


def amounts(text: str) -> set[int]:
    """Euro amounts written in the text: '1.963 €', '€ 1 966', '1,966 €', '695 euro'."""
    return {_to_int(raw) for raw in _matches(text)}


def _walk(value: Any, numbers: set[int]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        numbers.add(int(value))
    elif isinstance(value, str):
        numbers.update(amounts(value))
        if value.strip().startswith(("{", "[")):  # tool results arrive as JSON strings
            try:
                _walk(json.loads(value), numbers)
            except ValueError:
                pass
    elif isinstance(value, dict):
        for item in value.values():
            _walk(item, numbers)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _walk(item, numbers)


def known_numbers(*sources: Any) -> set[int]:
    """Every amount in the facts, plus the pairwise differences of the ones from 10 € up."""
    numbers: set[int] = set()
    for source in sources:
        _walk(source, numbers)
    numbers |= {abs(a - b) for a, b in combinations(sorted(n for n in numbers if n >= 10), 2)}
    return numbers


def ungrounded_amounts(text: str, *sources: Any) -> list[int]:
    known = known_numbers(*sources)
    wrong = []
    for raw in _matches(text):
        value = _to_int(raw)
        if value in known:
            continue
        if " " in raw and _to_int(raw.rsplit(" ", 1)[1]) in known:
            continue  # "giorno 2 150 €": a count followed by a known price, not 2150 €
        wrong.append(value)
    return sorted(set(wrong))


# Field names of the facts that models sometimes print as labels ("*perché*:", "**Varianti mancanti**:").
_FIELD_LABEL = re.compile(
    r"\*{1,2}\s*(perch[ée]|decisioni prese|scelte del sistema|varianti mancanti|giorni di viaggio|periodo|già noto)"
    r"\s*\*{1,2}\s*:\s*(\w?)",
    re.IGNORECASE,
)


_INLINE_LABEL = re.compile(r"\*{1,2}(periodo|perch[ée])\*{1,2}\s+(?=dal|dall'|\w)", re.IGNORECASE)


def strip_field_labels(text: str) -> str:
    text = _FIELD_LABEL.sub(lambda m: m.group(2).upper(), text)
    return _INLINE_LABEL.sub("", text)  # "– **periodo** dal 18 al 23 ottobre"
