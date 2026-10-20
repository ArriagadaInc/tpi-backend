"""Static contract checks for the SIM-HISTORIAL-LINEA-TIEMPO migration-009 SQL scripts.

These assertions lock the security-relevant markers of the forward/rollback scripts so the
contract is verifiable even without a live PostgreSQL (the full behavior is covered by
``tests/integration/test_audit_simulation_view.py``).
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_FORWARD = (_REPO_ROOT / "scripts" / "sql" / "009_create_historial_simulaciones.sql").read_text(
    encoding="utf-8"
)
_ROLLBACK = (_REPO_ROOT / "scripts" / "sql" / "009_drop_historial_simulaciones.sql").read_text(
    encoding="utf-8"
)


def test_forward_view_filters_simulation_events_and_projects_full_evidence() -> None:
    assert "CREATE OR REPLACE VIEW tpi.v_historial_simulaciones" in _FORWARD
    assert "security_barrier" in _FORWARD
    assert "accion = 'simulacion_renta_vitalicia'" in _FORWARD
    assert "tabla_afectada = 'tpi.leads'" in _FORWARD
    # Root functional metadata.
    assert "a.detalle->>'actor_subject' AS actor_subject" in _FORWARD
    assert "a.detalle->>'tipo_escenario' AS tipo_escenario" in _FORWARD
    assert "a.detalle->>'version_modelo' AS version_modelo" in _FORWARD
    assert "a.detalle->>'codigo_verificacion' AS codigo_verificacion" in _FORWARD
    # Complete evidence (no censoring): entradas + resultado as JSONB.
    assert "a.detalle->'entradas' AS entradas" in _FORWARD
    assert "a.detalle->'resultado' AS resultado" in _FORWARD
    # The raw detalle JSON is never projected as a whole, nor internal columns.
    assert "detalle AS" not in _FORWARD
    for forbidden in ("id_persona", "id_usuario", "ip_origen"):
        assert f"{forbidden} AS" not in _FORWARD


def test_forward_view_revokes_public_and_grants_only_app_role() -> None:
    assert "REVOKE ALL ON tpi.v_historial_simulaciones FROM PUBLIC" in _FORWARD
    assert "GRANT SELECT ON tpi.v_historial_simulaciones TO tpi_app" in _FORWARD
    # No GRANT statement over tpi.auditoria is introduced by the migration. (Comments
    # legitimately mention the absence of such grants, so only SQL statements count.)
    grant_lines = [
        line
        for line in _FORWARD.splitlines()
        if "GRANT" in line and "auditoria" in line and not line.strip().startswith("--")
    ]
    assert grant_lines == []


def test_forward_reuses_existing_support_index_and_creates_no_new_index() -> None:
    # 009 adds no new index: the timeline query is served by 008's support index
    # (accion, tabla_afectada, id_lead, fecha_hora), documented in the header comment.
    assert "CREATE INDEX" not in _FORWARD
    assert "auditoria_state_history_idx" in _FORWARD


def test_rollback_revokes_select_and_drops_view_only() -> None:
    assert "REVOKE SELECT ON tpi.v_historial_simulaciones FROM tpi_app" in _ROLLBACK
    assert "DROP VIEW tpi.v_historial_simulaciones" in _ROLLBACK
    # The rollback never drops the 008 support index nor touches audit data.
    assert "DROP INDEX" not in _ROLLBACK
    assert "DELETE FROM tpi.auditoria" not in _ROLLBACK


def test_forward_and_rollback_are_separate_transactional_scripts() -> None:
    assert _FORWARD.strip().startswith("--")
    assert "BEGIN;" in _FORWARD
    assert "COMMIT;" in _FORWARD
    assert "BEGIN;" in _ROLLBACK
    assert "COMMIT;" in _ROLLBACK


def test_009_does_not_modify_or_execute_005_006_007_008() -> None:
    for script in (_FORWARD, _ROLLBACK):
        # 009 must never DROP/ALTER objects owned by 005/006/007/008.
        assert "v_asignacion_auditoria" not in script
        assert "v_historial_estado_lead" not in script
        assert "asignaciones_one_active_per_lead_uq" not in script
