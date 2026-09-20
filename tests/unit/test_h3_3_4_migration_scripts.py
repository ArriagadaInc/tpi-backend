"""Static contract checks for the H3.3.4 migration-008 SQL scripts.

These assertions lock the security-relevant markers of the forward/rollback scripts so
the contract is verifiable even without a live PostgreSQL (the full behavior is covered
by ``tests/integration/test_audit_state_view.py``).
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_FORWARD = (_REPO_ROOT / "scripts" / "sql" / "008_create_lead_state_history.sql").read_text(
    encoding="utf-8"
)
_ROLLBACK = (_REPO_ROOT / "scripts" / "sql" / "008_drop_lead_state_history.sql").read_text(
    encoding="utf-8"
)


def test_forward_view_projects_only_sanitized_state_change_events() -> None:
    assert "CREATE OR REPLACE VIEW tpi.v_historial_estado_lead" in _FORWARD
    assert "security_barrier" in _FORWARD
    assert "accion = 'cambio_estado_lead'" in _FORWARD
    assert "tabla_afectada = 'tpi.leads'" in _FORWARD
    assert "a.detalle->>'actor_subject' AS actor_subject" in _FORWARD
    assert "a.detalle->>'estado_anterior' AS estado_anterior" in _FORWARD
    assert "a.detalle->>'estado_nuevo' AS estado_nuevo" in _FORWARD
    # The raw JSON is never projected as a column.
    assert "detalle AS" not in _FORWARD
    # PII / internal columns are never projected.
    for forbidden in ("id_persona", "id_usuario", "ip_origen"):
        assert f"{forbidden} AS" not in _FORWARD


def test_forward_view_revokes_public_and_grants_only_app_role() -> None:
    assert "REVOKE ALL ON tpi.v_historial_estado_lead FROM PUBLIC" in _FORWARD
    assert "GRANT SELECT ON tpi.v_historial_estado_lead TO tpi_app" in _FORWARD
    # No GRANT statement over tpi.auditoria is introduced by the migration. (The
    # support index legitimately references `ON tpi.auditoria` in its DDL, so the
    # check targets GRANT lines specifically.)
    grant_lines = [
        line for line in _FORWARD.splitlines() if "GRANT" in line and "auditoria" in line
    ]
    assert grant_lines == []


def test_forward_creates_explain_justified_support_index() -> None:
    assert "auditoria_state_history_idx" in _FORWARD
    assert "(accion, tabla_afectada, id_lead, fecha_hora)" in _FORWARD
    assert "CREATE INDEX IF NOT EXISTS" in _FORWARD


def test_rollback_revokes_select_and_drops_view_and_index() -> None:
    assert "REVOKE SELECT ON tpi.v_historial_estado_lead FROM tpi_app" in _ROLLBACK
    assert "DROP VIEW tpi.v_historial_estado_lead" in _ROLLBACK
    assert "DROP INDEX tpi.auditoria_state_history_idx" in _ROLLBACK


def test_forward_and_rollback_are_separate_transactional_scripts() -> None:
    assert _FORWARD.strip().startswith("--")
    assert "BEGIN;" in _FORWARD
    assert "COMMIT;" in _FORWARD
    assert "BEGIN;" in _ROLLBACK
    assert "COMMIT;" in _ROLLBACK


def test_008_does_not_modify_or_execute_005_006_007() -> None:
    for script in (_FORWARD, _ROLLBACK):
        # 008 must never DROP/ALTER objects owned by 005/006/007 nor reference them
        # as its own dependency to modify.
        assert "v_asignacion_auditoria" not in script
        assert "asignaciones_one_active_per_lead_uq" not in script
