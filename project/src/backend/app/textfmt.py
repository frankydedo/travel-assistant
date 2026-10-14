"""Italian formatting shared by template replies (mock provider, system messages)."""

from app.domain.requirements import MONTHS_IT


def eur(value: int) -> str:
    return f"{value:,}".replace(",", ".") + " €"


def day_it(iso: str) -> str:
    _, month, day = (int(x) for x in iso.split("-"))
    return f"{day} {MONTHS_IT[month - 1]}"
