"""Contract tests for canonical CRM lead states."""

from __future__ import annotations

import pytest

from app.models.crm_states import (
    CRM_STATE_CONTRACT,
    crm_state_aggregate_key,
    crm_state_filter_terms,
    crm_state_label,
    crm_state_tone,
    normalize_crm_state_for_display,
    normalize_crm_state_for_filter,
    normalize_crm_state_for_write,
)
from app.repositories.solicitud_repository import SolicitudRepository


def test_crm_state_contract_exposes_thirteen_canonical_values() -> None:
    assert len(CRM_STATE_CONTRACT) == 13
    assert CRM_STATE_CONTRACT == (
        "nuevo",
        "prospecto",
        "asignado",
        "contactado",
        "citado",
        "en_tramite",
        "expediente",
        "ficha_generada",
        "cerrado",
        "perdido",
        "no_califica",
        "duplicado",
        "dormido",
    )


def test_repository_returns_canonical_states_independent_of_database_content() -> None:
    assert SolicitudRepository.get_crm_estado_lead_options() == list(CRM_STATE_CONTRACT)


def test_crm_state_display_labels_cover_canonical_and_approved_aliases() -> None:
    assert crm_state_label("nuevo") == "Nuevo"
    assert crm_state_label("pendiente") == "Nuevo"
    assert crm_state_label("Citado") == "Citado"
    assert crm_state_label("En trámite") == "En trámite"
    assert crm_state_label("Cerrado") == "Cerrado"


def test_crm_state_display_is_fail_closed_for_ambiguous_values() -> None:
    assert crm_state_label("simulada") == "simulada"
    assert crm_state_label("en gestion") == "en gestion"
    assert normalize_crm_state_for_display("simulada") is None
    assert normalize_crm_state_for_display("en gestion") is None
    assert crm_state_tone("simulada") == "warning"


def test_crm_state_filter_terms_expand_approved_aliases() -> None:
    assert crm_state_filter_terms("nuevo") == ("nuevo", "pendiente")
    assert crm_state_filter_terms("pendiente") == ("nuevo", "pendiente")
    assert crm_state_filter_terms("En trámite") == ("en_tramite", "en trámite")
    assert crm_state_filter_terms("Cerrado") == ("cerrado",)
    assert normalize_crm_state_for_filter("Pendiente") == "nuevo"


def test_crm_state_aggregate_key_merges_legacy_pending_with_nuevo() -> None:
    assert crm_state_aggregate_key("nuevo") == "nuevo"
    assert crm_state_aggregate_key("pendiente") == "nuevo"
    assert crm_state_aggregate_key("Pendiente") == "nuevo"
    assert crm_state_aggregate_key("aprobada") == "aprobada"
    assert crm_state_aggregate_key("simulada") == "simulada"


def test_repository_filter_expands_nuevo_to_legacy_pending_server_side() -> None:
    clause, params = SolicitudRepository._build_crm_query_filters(estado_lead="nuevo")
    assert "LOWER(TRIM(l.estado_lead)) IN (%s, %s)" in clause
    assert params == ["nuevo", "pendiente"]


def test_crm_state_write_validation_accepts_only_canonical_values() -> None:
    assert normalize_crm_state_for_write("nuevo") == "nuevo"
    assert normalize_crm_state_for_write("contactado") == "contactado"
    with pytest.raises(ValueError):
        normalize_crm_state_for_write("pendiente")
    with pytest.raises(ValueError):
        normalize_crm_state_for_write("Nuevo")
    with pytest.raises(ValueError):
        normalize_crm_state_for_write("estado-inventado")
