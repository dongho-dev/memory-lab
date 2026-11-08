"""USD per million tokens (input, output) for cost estimates.

Source: https://platform.claude.com/docs/en/models/overview (checked 2026-11-07).
Haiku is listed as "from", so treat its numbers as a floor. Update when prices change.
"""
from __future__ import annotations

PRICES = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    if model not in PRICES:
        return None
    pin, pout = PRICES[model]
    return (input_tokens * pin + output_tokens * pout) / 1_000_000
