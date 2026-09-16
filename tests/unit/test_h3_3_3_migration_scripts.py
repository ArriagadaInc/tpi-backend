"""Static contract checks for the H3.3.3 migration-007 SQL scripts.

These assertions lock the security-relevant markers of the forward/rollback scripts so
the contract is verifiable even without a live PostgreSQL (the full behavior is covered
by ``tests/integration/test_audit_assignment_view.py``).
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_FORWARD = (_REPO_ROOT / "scripts" / "sql" / "007_create_audit_assignment_view.sql").read_text(
    encoding="utf-8"
)
_ROLLBACK = (_REPO_ROOT / "scripts" / "sql" / "007_drop_audit_assignment_view.sql").read_text(
    encoding="utf-8"
)


def test_forward_view_projects_only_sanitized_assignment_events() -> None:
    assert "CREATE OR REPLACE VIEW tpi.v_asignacion_auditoria" in _FORWARD
    assert "security_barrier" in _FORWARD
    assert "accion = 'asignacion_lead'" in _FORWARD
    assert "tabla_afectada = 'tpi.asignaciones'" in _FORWARD
    assert "a.detalle->>'actor_subject' AS actor_subject" in _FORWARD
    assert "a.detalle->>'id_asesor'" in _FORWARD
    assert "a.detalle->>'estado_anterior' AS estado_anterior" in _FORWARD
    assert "a.detalle->>'estado_nuevo' AS estado_nuevo" in _FORWARD
    # The raw JSON is never projected as a column.
    assert "detalle AS" not in _FORWARD


def test_forward_view_validates_uuid_with_case_insensitive_canonical_regex() -> None:
    assert "~*" in _FORWARD
    assert "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'" in _FORWARD
    assert "::uuid" in _FORWARD


def test_forward_view_revokes_public_and_grants_only_app_role() -> None:
    assert "REVOKE ALL ON tpi.v_asignacion_auditoria FROM PUBLIC" in _FORWARD
    assert "GRANT SELECT ON tpi.v_asignacion_auditoria TO tpi_app" in _FORWARD
    # No direct grant over tpi.auditoria is introduced by the migration.
    assert "GRANT" in _FORWARD
    for grant_line in ("ON tpi.auditoria", "ON TABLE tpi.auditoria"):
        assert grant_line not in _FORWARD


def test_rollback_revokes_select_and_drops_view() -> None:
    assert "REVOKE SELECT ON tpi.v_asignacion_auditoria FROM tpi_app" in _ROLLBACK
    assert "DROP VIEW" in _ROLLBACK
    assert "v_asignacion_auditoria" in _ROLLBACK


def test_forward_and_rollback_are_separate_transactional_scripts() -> None:
    assert _FORWARD.strip().startswith("--")
    assert "BEGIN;" in _FORWARD
    assert "COMMIT;" in _FORWARD
    assert "BEGIN;" in _ROLLBACK
    assert "COMMIT;" in _ROLLBACK
