"""Italian formatting shared by template replies (mock provider, system messages)."""

from app.domain.requirements import MONTHS_IT


def eur(value: int) -> str:
    return f"{value:,}".replace(",", ".") + " €"


def day_it(iso: str) -> str:
    _, month, day = (int(x) for x in iso.split("-"))
    return f"{day} {MONTHS_IT[month - 1]}"


def plain_text(text: str) -> str:
    """The chat renders plain text: strip the markdown models add despite the instructions."""
    import re

    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
    text = re.sub(r"(?m)^\s*[-*]\s+", "• ", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
