"""Reference list prices for the cost estimate (ADR-0010).

The free tiers cost nothing: these prices answer "what would this cost in production". They come from
third-party trackers of the providers' public price lists and change over time, so they are configuration,
not truth. Unknown models get no cost (shown as "n/d"), never a guess.
"""

# USD per 1M tokens: (input, output)
PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-120b": (0.15, 0.60),  # Groq list price
    "openai/gpt-oss-20b": (0.075, 0.30),  # Groq list price
    "gemini-flash-lite-latest": (0.25, 1.50),  # alias of the latest Flash-Lite (3.1 at the time of writing)
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "rules-v1": (0.0, 0.0),  # the deterministic mock
}


def estimate_cost(model: str, input_tokens: int | None, output_tokens: int | None) -> dict[str, float] | None:
    price = PRICES_USD_PER_MTOK.get(model)
    if price is None or input_tokens is None or output_tokens is None:
        return None
    cost_in = input_tokens * price[0] / 1_000_000
    cost_out = output_tokens * price[1] / 1_000_000
    return {"input": round(cost_in, 8), "output": round(cost_out, 8), "total": round(cost_in + cost_out, 8)}
