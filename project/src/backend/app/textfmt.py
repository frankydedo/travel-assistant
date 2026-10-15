"""Italian formatting shared by template replies (mock provider, system messages)."""

from app.domain.requirements import MONTHS_IT


def eur(value: int) -> str:
    return f"{value:,}".replace(",", ".") + " €"


def period_it(start_iso: str, end_iso: str) -> str:
    """'dall'8 al 12 novembre', 'dal 1° al 7 aprile', 'dal 30 novembre al 4 dicembre'."""
    _, m1, d1 = (int(x) for x in start_iso.split("-"))
    _, m2, d2 = (int(x) for x in end_iso.split("-"))
    first = f"{d1}°" if d1 == 1 else str(d1)
    prefix = "dall'" if d1 in (8, 11) else "dal "
    start = first if m1 == m2 else f"{first} {MONTHS_IT[m1 - 1]}"
    end = "1°" if d2 == 1 else str(d2)
    return f"{prefix}{start} al {end} {MONTHS_IT[m2 - 1]}"


def day_it(iso: str) -> str:
    _, month, day = (int(x) for x in iso.split("-"))
    return f"{day} {MONTHS_IT[month - 1]}"


def of_budget(budget: int | None) -> str:
    """Suffix for a total: " su 1.500 €", or nothing to compare against when the budget is unlimited."""
    return f" su {eur(budget)}" if budget is not None else " (budget illimitato)"


def budget_value(budget: int | None) -> int | str:
    """Budget as the LLM sees it in tool results and reply facts."""
    return budget if budget is not None else "illimitato"
