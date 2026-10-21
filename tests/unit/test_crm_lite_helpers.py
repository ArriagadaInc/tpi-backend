"""Unit tests for CRM presentation helpers."""

from app.components.formatting import format_currency_clp


def test_format_currency_clp_formats_chilean_pesos() -> None:
    assert format_currency_clp(0) == "$0"
    assert format_currency_clp(1000) == "$1.000"
    assert format_currency_clp(1000000) == "$1.000.000"
    assert format_currency_clp(1234567) == "$1.234.567"
    assert format_currency_clp(None) == "N/A"
