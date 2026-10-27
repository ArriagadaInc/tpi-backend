"""Static contract checks for the CRM-AGENDA-4-HISTORIAL-MIGRACION migration-011 SQL scripts.

These assertions lock the security-relevant markers of the forward/rollback scripts so the
contract is verifiable even without a live PostgreSQL (the full behavior is covered by
``tests/integration/test_agenda_historial_view.py``).
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_FORWARD = (_REPO_ROOT / "scripts" / "sql" / "011_create_historial_agenda.sql").read_text(
    encoding="utf-8"
)
_ROLLBACK = (_REPO_ROOT / "scripts" / "sql" / "011_drop_historial_agenda.sql").read_text(
    encoding="utf-8"
)

_ACCIONES = (
    "cita_agendada",
    "cita_reagendada",
    "cita_cancelada",
    "cita_realizada",
    "cita_no_asistio",
)


def test_forward_y_rollback_son_transaccionales_y_empiezan_con_comentario() -> None:
    assert _FORWARD.strip().startswith("--")
    assert _ROLLBACK.strip().startswith("--")
    assert "BEGIN;" in _FORWARD
    assert "COMMIT;" in _FORWARD
    assert "BEGIN;" in _ROLLBACK
    assert "COMMIT;" in _ROLLBACK


def test_forward_crea_la_vista_con_security_barrier_y_filtro_fijo() -> None:
    assert "CREATE OR REPLACE VIEW tpi.v_historial_agenda" in _FORWARD
    assert "security_barrier" in _FORWARD
    for accion in _ACCIONES:
        assert f"'{accion}'" in _FORWARD
    assert (
        "accion IN ('cita_agendada', 'cita_reagendada', 'cita_cancelada', 'cita_realizada', 'cita_no_asistio')"
        in _FORWARD
    )
    assert "tabla_afectada = 'tpi.citas'" in _FORWARD


def test_forward_proyecta_solo_las_columnas_del_contrato() -> None:
    assert "a.id_auditoria," in _FORWARD
    assert "a.id_lead," in _FORWARD
    assert "a.fecha_hora," in _FORWARD
    assert "a.accion," in _FORWARD
    assert "a.detalle->>'actor_subject' AS actor_subject" in _FORWARD
    assert "END AS id_cita" in _FORWARD
    assert "END AS responsable_id" in _FORWARD
    assert "a.detalle->>'estado_anterior' AS estado_anterior" in _FORWARD
    assert "a.detalle->>'estado_nuevo' AS estado_nuevo" in _FORWARD
    assert "(a.detalle->>'fecha_hora_anterior')::timestamptz AS fecha_hora_anterior" in _FORWARD
    assert "(a.detalle->>'fecha_hora_nueva')::timestamptz AS fecha_hora_nueva" in _FORWARD
    # El detalle crudo nunca se proyecta como un todo, ni las columnas internas.
    assert "detalle AS" not in _FORWARD
    for forbidden in ("id_persona", "id_usuario", "ip_origen"):
        assert f"{forbidden} AS" not in _FORWARD


def test_forward_contiene_el_preflight_de_privilegios() -> None:
    assert "has_schema_privilege('tpi_app', 'tpi', 'USAGE')" in _FORWARD
    assert "has_table_privilege('tpi_app', 'tpi.auditoria', 'SELECT')" in _FORWARD
    assert "has_table_privilege('tpi_app', 'tpi.auditoria', 'UPDATE')" in _FORWARD
    assert "has_table_privilege('tpi_app', 'tpi.auditoria', 'DELETE')" in _FORWARD
    assert "011 preflight failed" in _FORWARD


def test_forward_revoca_public_y_concede_solo_a_app() -> None:
    assert "REVOKE ALL ON tpi.v_historial_agenda FROM PUBLIC" in _FORWARD
    assert "GRANT SELECT ON tpi.v_historial_agenda TO tpi_app" in _FORWARD
    # No se introduce ningun GRANT sobre tpi.auditoria (los comentarios no cuentan).
    grant_lines = [
        line
        for line in _FORWARD.splitlines()
        if "GRANT" in line and "auditoria" in line and not line.strip().startswith("--")
    ]
    assert grant_lines == []


def test_forward_no_crea_indice_nuevo_y_reutiliza_el_de_008() -> None:
    assert "CREATE INDEX" not in _FORWARD
    assert "auditoria_state_history_idx" in _FORWARD


def test_rollback_revoca_select_y_drop_view_solo() -> None:
    assert "REVOKE SELECT ON tpi.v_historial_agenda FROM tpi_app" in _ROLLBACK
    assert "DROP VIEW IF EXISTS tpi.v_historial_agenda" in _ROLLBACK
    assert "DROP INDEX" not in _ROLLBACK
    assert "DELETE FROM tpi.auditoria" not in _ROLLBACK


def test_011_no_modifica_ni_ejecuta_007_008_009_010() -> None:
    for script in (_FORWARD, _ROLLBACK):
        assert "v_asignacion_auditoria" not in script
        assert "v_historial_estado_lead" not in script
        assert "v_historial_simulaciones" not in script
