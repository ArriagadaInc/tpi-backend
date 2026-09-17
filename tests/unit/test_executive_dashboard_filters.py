"""Unit tests for the validated executive-dashboard filter object."""

from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from app.models.executive_dashboard import (
    GRANULARITY_VALUES,
    DashboardFilters,
    granularity_sql_field,
    percentage,
)


def test_defaults_are_safe() -> None:
    filters = DashboardFilters.from_raw()
    assert filters.fecha_desde is None
    assert filters.fecha_hasta is None
    assert filters.granularidad == "diaria"
    assert filters.estado is None
    assert filters.asesor is None
    assert filters.afp is None
    assert filters.origen is None
    assert filters.fuente is None
    assert filters.period_active is False


@pytest.mark.parametrize("value", list(GRANULARITY_VALUES))
def test_granularity_whitelist_accepts_valid_values(value: str) -> None:
    filters = DashboardFilters.from_raw(granularidad=value)
    assert filters.granularidad == value
    assert granularity_sql_field(value) in {"day", "week", "month"}


def test_granularity_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        DashboardFilters.from_raw(granularidad="horaria")


def test_granularity_rejects_empty_injection_of_invalid_value() -> None:
    with pytest.raises(ValueError):
        DashboardFilters.from_raw(granularidad="dia")


def test_invalid_date_range_is_rejected() -> None:
    with pytest.raises(ValueError):
        DashboardFilters.from_raw(fecha_desde="2026-09-20", fecha_hasta="2026-09-01")


def test_date_boundaries_are_inclusive_and_parsed() -> None:
    filters = DashboardFilters.from_raw(fecha_desde="2026-09-01", fecha_hasta="2026-09-01")
    assert filters.fecha_desde == date(2026, 9, 1)
    assert filters.fecha_hasta == date(2026, 9, 1)
    assert filters.period_active is True


def test_invalid_iso_date_is_rejected() -> None:
    with pytest.raises(ValueError):
        DashboardFilters.from_raw(fecha_desde="not-a-date")


def test_estado_is_normalized_to_lowercase() -> None:
    filters = DashboardFilters.from_raw(estado="Nuevo")
    assert filters.estado == "nuevo"


def test_unknown_estado_is_preserved_for_safe_filtering() -> None:
    filters = DashboardFilters.from_raw(estado="estado_raro")
    assert filters.estado == "estado_raro"


def test_asesor_and_afp_parse_valid_uuids() -> None:
    asesor = "44444444-4444-4444-4444-444444444441"
    afp = "00000000-0000-0000-0000-000000000001"
    filters = DashboardFilters.from_raw(asesor=asesor, afp=afp)
    assert filters.asesor == UUID(asesor)
    assert filters.afp == UUID(afp)


@pytest.mark.parametrize("field", ["asesor", "afp"])
def test_invalid_uuid_is_rejected(field: str) -> None:
    with pytest.raises(ValueError):
        DashboardFilters.from_raw(**{field: "no-es-un-uuid"})


def test_origen_and_fuente_are_stripped_and_empty_becomes_none() -> None:
    filters = DashboardFilters.from_raw(origen="  formulario_web  ", fuente="")
    assert filters.origen == "formulario_web"
    assert filters.fuente is None


def test_to_dict_is_json_safe() -> None:
    filters = DashboardFilters.from_raw(
        fecha_desde="2026-09-01",
        asesor="44444444-4444-4444-4444-444444444441",
    )
    payload = filters.to_dict()
    assert payload["fecha_desde"] == "2026-09-01"
    assert payload["fecha_hasta"] is None
    assert payload["asesor"] == "44444444-4444-4444-4444-444444444441"


def test_percentage_includes_numerator_and_denominator_semantics() -> None:
    assert percentage(3, 4) == 0.75
    assert percentage(0, 0) is None
    assert percentage(5, 0) is None
