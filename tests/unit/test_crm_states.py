"""Contract tests for canonical CRM lead states."""

from __future__ import annotations

import pytest

from app.models.crm_states import (
    CRM_STATE_CONTRACT,
    CRM_STATE_LABELS,
    CRM_STATE_TONES,
    crm_state_aggregate_key,
    crm_state_filter_terms,
    crm_state_label,
    crm_state_tone,
    normalize_crm_state_for_display,
    normalize_crm_state_for_filter,
    normalize_crm_state_for_write,
)
from app.repositories.solicitud_repository import SolicitudRepository


def test_crm_state_contract_exposes_twelve_canonical_values() -> None:
    assert len(CRM_STATE_CONTRACT) == 12
    assert CRM_STATE_CONTRACT == (
        "nuevo",
        "asignado",
        "sin_contacto",
        "en_seguimiento",
        "reunion_agendada",
        "reunion_realizada",
        "ficha_generada",
        "cerrado",
        "no_interesado",
        "datos_erroneos",
        "no_contactado",
        "perdido",
    )


def test_crm_state_labels_keep_their_accents() -> None:
    assert CRM_STATE_LABELS["reunion_agendada"] == "Reunión agendada"
    assert CRM_STATE_LABELS["reunion_realizada"] == "Reunión realizada"
    assert CRM_STATE_LABELS["datos_erroneos"] == "Datos erróneos"
    assert CRM_STATE_LABELS["sin_contacto"] == "Sin contacto"
    assert CRM_STATE_LABELS["en_seguimiento"] == "En seguimiento"
    assert CRM_STATE_LABELS["no_interesado"] == "No interesado"
    assert CRM_STATE_LABELS["no_contactado"] == "No contactado"


def test_crm_state_tones_cover_every_contract_state() -> None:
    assert set(CRM_STATE_TONES) == set(CRM_STATE_CONTRACT)
    assert CRM_STATE_TONES["nuevo"] == "info"
    assert CRM_STATE_TONES["sin_contacto"] == "warning"
    assert CRM_STATE_TONES["reunion_agendada"] == "success"
    assert CRM_STATE_TONES["no_interesado"] == "error"
    assert CRM_STATE_TONES["perdido"] == "error"


def test_repository_returns_canonical_states_independent_of_database_content() -> None:
    assert SolicitudRepository.get_crm_estado_lead_options() == list(CRM_STATE_CONTRACT)


def test_crm_state_display_labels_cover_canonical_and_approved_aliases() -> None:
    assert crm_state_label("nuevo") == "Nuevo"
    assert crm_state_label("pendiente") == "Nuevo"
    assert crm_state_label("reunion_agendada") == "Reunión agendada"
    assert crm_state_label("datos_erroneos") == "Datos erróneos"
    assert crm_state_label("Cerrado") == "Cerrado"


def test_crm_state_display_is_fail_closed_for_ambiguous_values() -> None:
    assert crm_state_label("simulada") == "simulada"
    assert crm_state_label("en gestion") == "en gestion"
    assert crm_state_label("prospecto") == "prospecto"  # retired state shown verbatim
    assert normalize_crm_state_for_display("simulada") is None
    assert normalize_crm_state_for_display("en gestion") is None
    assert normalize_crm_state_for_display("prospecto") is None
    assert crm_state_tone("simulada") == "warning"


def test_unknown_saved_state_is_preserved_without_error() -> None:
    assert crm_state_label("estado_desconocido_xyz") == "estado_desconocido_xyz"
    assert normalize_crm_state_for_display("estado_desconocido_xyz") is None
    assert crm_state_tone("estado_desconocido_xyz") == "warning"
    assert crm_state_aggregate_key("estado_desconocido_xyz") == "estado_desconocido_xyz"


def test_crm_state_filter_terms_expand_approved_aliases() -> None:
    assert crm_state_filter_terms("nuevo") == ("nuevo", "pendiente")
    assert crm_state_filter_terms("pendiente") == ("nuevo", "pendiente")
    assert crm_state_filter_terms("Cerrado") == ("cerrado",)
    assert crm_state_filter_terms("reunion_agendada") == ("reunion_agendada",)
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
    assert normalize_crm_state_for_write("sin_contacto") == "sin_contacto"
    assert normalize_crm_state_for_write("reunion_agendada") == "reunion_agendada"
    with pytest.raises(ValueError):
        normalize_crm_state_for_write("pendiente")
    with pytest.raises(ValueError):
        normalize_crm_state_for_write("Nuevo")
    with pytest.raises(ValueError):
        normalize_crm_state_for_write("estado-inventado")
    # Retired states are no longer part of the contract and are rejected on write.
    for retired in (
        "prospecto",
        "contactado",
        "citado",
        "en_tramite",
        "expediente",
        "no_califica",
        "duplicado",
        "dormido",
    ):
        with pytest.raises(ValueError):
            normalize_crm_state_for_write(retired)
