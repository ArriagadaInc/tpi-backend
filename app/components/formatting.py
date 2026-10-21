"""Pure formatting helpers for the web CRM layer."""

from __future__ import annotations

from typing import Any


def format_currency_clp(value: Any) -> str:
    """Format a numeric value as Chilean pesos without introducing locale dependencies."""
    if value is None:
        return "N/A"
    try:
        amount = int(value)
    except (TypeError, ValueError):
        try:
            amount = int(float(value))
        except (TypeError, ValueError):
            return "N/A"
    return f"${amount:,}".replace(",", ".")
