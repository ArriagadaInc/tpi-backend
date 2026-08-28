"""Focused unit tests for web-layer helper functions."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

import app.web.dependencies as web_dependencies
from app.config import Settings
from app.web.dependencies import (
    _as_date,
    _MockLeadBoardService,
    _row_date,
    build_service_for_web,
    get_web_service,
    has_real_data_source,
    resolve_web_simulator_url,
)
from app.web.presentation import parse_lead_comments
from app.web.routes.leads import (
    _build_detail_redirect_url_from_value,
    _build_query_url,
    _parse_date,
    _parse_int,
    _sanitize_return_to,
)


class _DummyService:
    pass


class _DummyFactory:
    def __call__(self) -> _DummyService:
        return _DummyService()


def test_dependency_helpers_reuse_real_service_and_resolve_simulator_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dummy = _DummyService()
    assert build_service_for_web(dummy) is dummy
    assert has_real_data_source(dummy) is True
    assert has_real_data_source(_MockLeadBoardService()) is False

    service = get_web_service(factory=_DummyFactory())
    assert isinstance(service, _DummyService)

    monkeypatch.setattr(
        web_dependencies,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            APP_ENV="aws-dev",
            TPI_PUBLIC_SITE_URL="https://backoffice.dev.tupensioninteligente.cl/",
        ),
    )
    assert resolve_web_simulator_url() == (
        "https://backoffice.dev.tupensioninteligente.cl/simulador.html#simulador-interactivo"
    )


def test_mock_web_service_filters_sorts_and_updates_rows() -> None:
    service = _MockLeadBoardService()
    board = service.get_crm_bandeja(
        page=1,
        page_size=5,
        search="Maria",
        estado_lead="contactado",
        afp_id="00000000-0000-0000-0000-000000000002",
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        sort_by="nombre_completo",
        sort_direction="asc",
    )
    assert board["page"] == 1
    assert board["page_size"] == 5
    assert board["total"] >= 1
    assert board["solicitudes"][0]["nombre_completo"] == "Maria Soto"

    rut_board = service.get_crm_bandeja(sort_by="rut", sort_direction="desc")
    assert rut_board["solicitudes"][0]["rut"] >= rut_board["solicitudes"][-1]["rut"]

    created_board = service.get_crm_bandeja(sort_by="created_at", sort_direction="desc")
    assert (
        created_board["solicitudes"][0]["created_at"]
        >= created_board["solicitudes"][-1]["created_at"]
    )

    lead_id = "11111111-1111-1111-1111-111111111111"
    assert service.get_solicitud_detalle(lead_id) is not None
    assert service.get_solicitud_detalle_masked(lead_id) is not None
    assert service.update_lead_status(lead_id, "contactado") is True
    assert service.update_lead_status(lead_id, "cerrado") is True
    assert service.get_solicitud_detalle(lead_id)["estado_lead"] == "cerrado"
    assert service.append_lead_comment(lead_id, "Nota de seguimiento", "Alvaro Local") is True
    matching = service.get_solicitudes_por_rut("12.345.678-5")
    assert matching
    assert matching[0]["rut"] == "12.345.678-5"
    cleanup = service.delete_test_lead(lead_id)
    assert cleanup is None
    assert service.is_test_lead_cleanup_enabled() is True


def test_web_route_helpers_accept_only_safe_internal_values() -> None:
    assert _build_query_url("/leads", {"search": "Pérez", "page": 2, "empty": ""}) == (
        "/leads?search=P%C3%A9rez&page=2"
    )
    assert _sanitize_return_to("/leads?page=2&search=Perez") == "/leads?page=2&search=Perez"
    assert _sanitize_return_to("https://evil.example") is None
    assert _sanitize_return_to("//evil.example") is None
    assert _sanitize_return_to("/admin") is None
    assert _build_detail_redirect_url_from_value("123", "https://evil.example") == (
        "/leads/123?return_to=%2Fleads"
    )

    assert _parse_date("2026-08-23") == date(2026, 8, 23)
    assert _parse_date(None) is None
    with pytest.raises(ValueError):
        _parse_date("invalid-date")

    assert _parse_int(None, 10) == 10
    assert _parse_int("0", 10) == 1
    assert _parse_int("-4", 10) == 1
    assert _parse_int("abc", 10) == 10


def test_web_comment_parser_fails_closed_for_empty_follow_up_block() -> None:
    parsed = parse_lead_comments(
        "Solicitud original.\n\n\n\n[23/08/2026 22:32] Alvaro Local\nCliente contactado."
    )
    assert parsed.original_request == (
        "Solicitud original.\n\n\n\n[23/08/2026 22:32] Alvaro Local\nCliente contactado."
    )
    assert parsed.notes == []
    assert parsed.is_fallback is True


def test_web_date_helpers_accept_datetime_and_plain_date_values() -> None:
    moment = datetime(2026, 8, 23, 10, 15, tzinfo=UTC)
    assert _row_date({"created_at": moment}) == date(2026, 8, 23)
    assert _row_date({"created_at": date(2026, 8, 22)}) == date(2026, 8, 22)
    assert _as_date("2026-08-23") == date(2026, 8, 23)
