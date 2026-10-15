"""Travel days (ADR-0023): how much of the first and last day is left around the flights.

Times are local at each airport ("HH:MM", "+1" when the flight lands the next day). An activity fits a
travel day only if its duration fits the free window; otherwise that day is a travel day without an
activity, declared in the itinerary instead of scheduling something the travellers cannot attend.
"""

DAY_START = 9.0  # activities start no earlier than this
DAY_END = 22.0  # and end no later than this
ARRIVAL_BUFFER = 1.5  # hours from landing to being free (passport, transfer, hotel)
DEPARTURE_BUFFER = 2.5  # hours to be at the airport before take-off


def _clock(value: str) -> tuple[float, int]:
    """'07:47' -> (7.78, 0); '01:25+1' -> (1.42, 1)."""
    time, _, offset = value.partition("+")
    hours, minutes = time.split(":")
    return int(hours) + int(minutes) / 60, int(offset or 0)


def arrival_window(arrival_time: str) -> float:
    """Free hours on the first day after landing (0 when landing after midnight)."""
    hour, next_day = _clock(arrival_time)
    if next_day:
        return 0.0
    return max(0.0, DAY_END - max(DAY_START, hour + ARRIVAL_BUFFER))


def departure_window(departure_time: str) -> float:
    """Free hours on the last day before leaving for the airport."""
    hour, _ = _clock(departure_time)
    return max(0.0, min(DAY_END, hour - DEPARTURE_BUFFER) - DAY_START)


def describe_arrival(arrival_time: str) -> str:
    hour, next_day = _clock(arrival_time)
    return f"arrivo alle {arrival_time.partition('+')[0]}" + (" del giorno dopo" if next_day else "")


def describe_departure(departure_time: str) -> str:
    return f"volo di ritorno alle {departure_time}"
