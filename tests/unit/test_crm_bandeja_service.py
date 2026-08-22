"""Unit tests for CRM Lite board service behavior."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from app.services.solicitud_service import SolicitudService


class _RepositoryStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def get_crm_solicitudes(self, **kwargs):
        self.calls.append(kwargs)
        return ([], 0)

    def get_crm_estado_lead_options(self) -> list[str]:
        return ["pendiente", "aprobada", "descartado"]


CRM_TZ = ZoneInfo("America/Santiago")


def test_crm_bandeja_rejects_invalid_pagination() -> None:
    service = SolicitudService(repository=cast(Any, _RepositoryStub()))

    with pytest.raises(ValueError, match="page must be greater than zero"):
        service.get_crm_bandeja(page=0)

    with pytest.raises(ValueError, match="page_size must be greater than zero"):
        service.get_crm_bandeja(page_size=0)


def test_crm_bandeja_rejects_inverted_date_range() -> None:
    service = SolicitudService(repository=cast(Any, _RepositoryStub()))

    with pytest.raises(ValueError, match="date_from cannot be greater than date_to"):
        service.get_crm_bandeja(date_from=date(2026, 8, 20), date_to=date(2026, 8, 19))


def test_crm_bandeja_normalizes_dates_to_aware_datetimes() -> None:
    repo = _RepositoryStub()
    service = SolicitudService(repository=cast(Any, repo))
    afp_id = UUID("11111111-1111-1111-1111-111111111111")

    service.get_crm_bandeja(
        search="alvaro",
        estado_lead="pendiente",
        afp_id=afp_id,
        date_from=date(2026, 8, 20),
        date_to=datetime(2026, 8, 21, 12, 0),
        sort_by="nombre_completo",
        sort_direction="asc",
    )

    assert len(repo.calls) == 1
    call = repo.calls[0]
    assert call["search"] == "alvaro"
    assert call["estado_lead"] == "pendiente"
    assert call["afp_id"] == afp_id
    assert call["sort_by"] == "nombre_completo"
    assert call["sort_direction"] == "asc"
    assert isinstance(call["date_from"], datetime)
    assert isinstance(call["date_to"], datetime)
    assert call["date_from"].tzinfo is not None
    assert call["date_to"].tzinfo is not None


def test_crm_bandeja_normalizes_utc_dates_to_santiago_business_day() -> None:
    repo = _RepositoryStub()
    service = SolicitudService(repository=cast(Any, repo))

    service.get_crm_bandeja(
        date_from=datetime(2026, 8, 22, 0, 30, tzinfo=UTC),
        date_to=datetime(2026, 8, 22, 0, 30, tzinfo=UTC),
    )

    call = repo.calls[0]
    assert isinstance(call["date_from"], datetime)
    assert isinstance(call["date_to"], datetime)
    assert call["date_from"].astimezone(CRM_TZ).date().isoformat() == "2026-08-21"
    assert call["date_to"].astimezone(CRM_TZ).date().isoformat() == "2026-08-21"


def test_crm_estado_options_are_delegated() -> None:
    service = SolicitudService(repository=cast(Any, _RepositoryStub()))

    assert service.get_crm_estado_lead_options() == [
        "pendiente",
        "aprobada",
        "descartado",
    ]
