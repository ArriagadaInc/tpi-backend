"""Static contract checks for the CRM-AGENDA-1-MIGRACION migration-010 SQL scripts.

These assertions lock the structural markers of the forward/rollback scripts so the
contract is verifiable even without a live PostgreSQL (the full behavior is covered by
``tests/integration/test_citas_agenda_migration.py``).
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_FORWARD = (_REPO_ROOT / "scripts" / "sql" / "010_extend_citas_agenda.sql").read_text(
    encoding="utf-8"
)
_ROLLBACK = (_REPO_ROOT / "scripts" / "sql" / "010_drop_citas_agenda.sql").read_text(
    encoding="utf-8"
)

_COLUMNAS_NUEVAS = (
    "fecha_hora_fin",
    "agendada_por_subject",
    "agendada_por_nombre",
    "nota",
    "motivo_cancelacion",
    "updated_at",
)


def test_forward_y_rollback_son_transaccionales_y_empiezan_con_comentario() -> None:
    assert _FORWARD.strip().startswith("--")
    assert _ROLLBACK.strip().startswith("--")
    assert "BEGIN;" in _FORWARD
    assert "COMMIT;" in _FORWARD
    assert "BEGIN;" in _ROLLBACK
    assert "COMMIT;" in _ROLLBACK


def test_forward_crea_la_extension_btree_gist() -> None:
    # La restriccion EXCLUDE exige btree_gist; el preflight la intenta crear y aborta con
    # un mensaje claro si no puede.
    assert "CREATE EXTENSION IF NOT EXISTS btree_gist" in _FORWARD
    assert "btree_gist" in _FORWARD


def test_forward_agrega_las_columnas_nuevas_y_obliga_el_responsable() -> None:
    assert "ADD COLUMN fecha_hora_fin TIMESTAMPTZ NOT NULL" in _FORWARD
    for columna in _COLUMNAS_NUEVAS:
        assert f"ADD COLUMN {columna}" in _FORWARD
    assert "ALTER COLUMN id_asesor SET NOT NULL" in _FORWARD


def test_forward_agrega_los_checks_de_fecha_y_estado() -> None:
    assert "citas_fecha_hora_fin_gt_inicio_chk" in _FORWARD
    assert "fecha_hora_fin > fecha_hora" in _FORWARD
    assert "citas_estado_cita_check" in _FORWARD
    assert "'agendada', 'realizada', 'no_asistio', 'cancelada'" in _FORWARD


def test_forward_agrega_indices_y_restriccion_de_exclusion() -> None:
    # Una reunion agendada por lead.
    assert "citas_one_agendada_per_lead_uq" in _FORWARD
    assert "WHERE estado_cita = 'agendada'" in _FORWARD
    # Indice de lectura por fecha_hora.
    assert "citas_fecha_hora_idx" in _FORWARD
    # El responsable no se pisa.
    assert "citas_responsable_no_superposicion_excl" in _FORWARD
    assert "EXCLUDE USING gist" in _FORWARD
    assert "tstzrange(fecha_hora, fecha_hora_fin)" in _FORWARD


def test_forward_agrega_atiende_reuniones_en_asesores() -> None:
    assert "ADD COLUMN atiende_reuniones BOOLEAN NOT NULL DEFAULT false" in _FORWARD


def test_forward_concede_privilegios_minimos_sobre_citas() -> None:
    assert "REVOKE ALL ON tpi.citas FROM PUBLIC" in _FORWARD
    assert "GRANT SELECT, INSERT, UPDATE ON tpi.citas TO tpi_app" in _FORWARD
    # Nunca DELETE sobre tpi.citas.
    assert "DELETE ON tpi.citas" not in _FORWARD
    # No se introducen grants sobre tpi.auditoria ni sobre otras tablas.
    grant_lines = [
        line
        for line in _FORWARD.splitlines()
        if "GRANT" in line and not line.strip().startswith("--")
    ]
    assert grant_lines == ["GRANT SELECT, INSERT, UPDATE ON tpi.citas TO tpi_app;"]


def test_rollback_revoca_privilegios_y_quita_indices_restricciones_y_columnas() -> None:
    assert "REVOKE SELECT, INSERT, UPDATE ON tpi.citas FROM tpi_app" in _ROLLBACK
    assert "DROP CONSTRAINT IF EXISTS citas_responsable_no_superposicion_excl" in _ROLLBACK
    assert "DROP INDEX IF EXISTS tpi.citas_one_agendada_per_lead_uq" in _ROLLBACK
    assert "DROP INDEX IF EXISTS tpi.citas_fecha_hora_idx" in _ROLLBACK
    assert "DROP CONSTRAINT IF EXISTS citas_estado_cita_check" in _ROLLBACK
    assert "DROP CONSTRAINT IF EXISTS citas_fecha_hora_fin_gt_inicio_chk" in _ROLLBACK
    for columna in _COLUMNAS_NUEVAS:
        assert f"DROP COLUMN IF EXISTS {columna}" in _ROLLBACK
    # Revertir el responsable obligatorio.
    assert "ALTER COLUMN id_asesor DROP NOT NULL" in _ROLLBACK
    assert "DROP COLUMN IF EXISTS atiende_reuniones" in _ROLLBACK


def test_rollback_no_elimina_tabla_ni_extension_ni_toca_auditoria() -> None:
    assert "DROP TABLE" not in _ROLLBACK
    assert "DROP EXTENSION" not in _ROLLBACK
    assert "DELETE FROM tpi.citas" not in _ROLLBACK
    # Ninguna sentencia SQL (fuera de comentarios) toca tpi.auditoria.
    auditoria_lines = [
        line
        for line in _ROLLBACK.splitlines()
        if "auditoria" in line and not line.strip().startswith("--")
    ]
    assert auditoria_lines == []


def test_010_no_modifica_ni_referencia_los_objetos_de_001_a_009() -> None:
    for script in (_FORWARD, _ROLLBACK):
        assert "v_asignacion_auditoria" not in script
        assert "v_historial_estado_lead" not in script
        assert "v_historial_simulaciones" not in script
        assert "asignaciones_one_active_per_lead_uq" not in script
