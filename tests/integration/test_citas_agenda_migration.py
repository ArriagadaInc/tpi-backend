"""Integration tests for CRM-AGENDA-1-MIGRACION (ampliacion de tpi.citas y tpi.asesores).

El bootstrap ``scripts/init_test_database.py`` crea ``tpi.citas`` en su forma final
(post-010) y ``tpi.asesores.atiende_reuniones``. Estas pruebas aplican el forward y la
reversa reales contra PostgreSQL (``scripts/sql/010_extend_citas_agenda.sql`` y
``scripts/sql/010_drop_citas_agenda.sql``) y demuestran las restricciones de la agenda:

  - dos reuniones agendadas del mismo responsable que se pisan se rechazan;
  - dos que no se pisan (una justo despues de la otra) se aceptan;
  - una reunion cancelada o realizada no bloquea el horario;
  - un lead no admite dos agendadas;
  - estado_cita invalido se rechaza;
  - fecha_hora_fin anterior al inicio se rechaza.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.errors import CheckViolation, ExclusionViolation, UniqueViolation

from app.config import get_settings
from app.database.connection import get_db_connection
from app.database.healthcheck import full_health_check

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FORWARD_SQL = (_REPO_ROOT / "scripts" / "sql" / "010_extend_citas_agenda.sql").read_text(
    encoding="utf-8"
)
_ROLLBACK_SQL = (_REPO_ROOT / "scripts" / "sql" / "010_drop_citas_agenda.sql").read_text(
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


@pytest.fixture(scope="session", autouse=True)
def verify_database() -> None:
    if not full_health_check().get("all_ready"):
        pytest.skip("Base de datos no disponible para tests de integración")


@pytest.fixture(scope="session", autouse=True)
def ensure_tpi_app_role() -> None:
    with get_db_connection(operation="integration.citas.ensure_tpi_app_role") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tpi_app') THEN
                        CREATE ROLE tpi_app NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
                    END IF;
                END
                $$;
                """)
        conn.commit()


def _apply_script(sql: str) -> None:
    with connect(get_settings().get_database_url(), autocommit=True) as conn:
        conn.execute(sql)


def _vaciar_citas() -> None:
    with get_db_connection(operation="integration.citas.vaciar") as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tpi.citas")
        conn.commit()


def _columna_existe(cur, tabla: str, columna: str) -> bool:
    cur.execute(
        "SELECT EXISTS ("
        "  SELECT 1 FROM information_schema.columns "
        "  WHERE table_schema = 'tpi' AND table_name = %s AND column_name = %s"
        ") AS existe",
        (tabla, columna),
    )
    return bool(cur.fetchone()["existe"])


def _es_not_null(cur, tabla: str, columna: str) -> bool:
    cur.execute(
        "SELECT is_nullable = 'NO' AS not_null FROM information_schema.columns "
        "WHERE table_schema = 'tpi' AND table_name = %s AND column_name = %s",
        (tabla, columna),
    )
    return bool(cur.fetchone()["not_null"])


def _constraint_existe(cur, nombre: str) -> bool:
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = %s) AS existe",
        (nombre,),
    )
    return bool(cur.fetchone()["existe"])


def _index_existe(cur, nombre: str) -> bool:
    cur.execute(
        "SELECT EXISTS ("
        "  SELECT 1 FROM pg_indexes WHERE schemaname = 'tpi' AND indexname = %s"
        ") AS existe",
        (nombre,),
    )
    return bool(cur.fetchone()["existe"])


def _public_tiene_privilegio_citas(cur) -> bool:
    cur.execute(
        "SELECT COALESCE((SELECT bool_or(grantee = 0) FROM aclexplode(relacl)), false) "
        "AS public_any FROM pg_class WHERE oid = 'tpi.citas'::regclass"
    )
    return bool(cur.fetchone()["public_any"])


def _make_asesor(cur, nombre: str) -> str:
    cur.execute(
        "INSERT INTO tpi.asesores (nombre, rol, estado_disponibilidad) "
        "VALUES (%s, 'asesor', 'activo') RETURNING id_asesor",
        (nombre,),
    )
    return str(cur.fetchone()["id_asesor"])


def _make_lead(cur, rut: str) -> str:
    cur.execute(
        "INSERT INTO tpi.personas (rut, nombre_completo, email, telefono) "
        "VALUES (%s, %s, %s, %s) RETURNING id_persona",
        (rut, "Agenda Integration", f"{rut}@example.com", "+56912345678"),
    )
    persona_id = str(cur.fetchone()["id_persona"])
    cur.execute(
        "INSERT INTO tpi.leads (id_persona, fecha_ingreso, estado_lead, origen_lead, fuente_actual) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id_lead",
        (persona_id, datetime.now(UTC), "nuevo", "integration", "integration"),
    )
    return str(cur.fetchone()["id_lead"])


def _insertar_cita(
    cur,
    *,
    id_lead: str,
    id_asesor: str,
    inicio: datetime,
    fin: datetime,
    estado: str = "agendada",
) -> None:
    cur.execute(
        "INSERT INTO tpi.citas (id_lead, id_asesor, fecha_hora, fecha_hora_fin, estado_cita) "
        "VALUES (%s, %s, %s, %s, %s)",
        (id_lead, id_asesor, inicio, fin, estado),
    )


def _hora(hh: int, mm: int = 0) -> datetime:
    return datetime(2026, 10, 1, hh, mm, tzinfo=UTC)


def test_forward_migration_aplica_y_verifica() -> None:
    _vaciar_citas()
    # El bootstrap deja tpi.citas en su forma final; la reversa lo deja en pre-010.
    _apply_script(_ROLLBACK_SQL)
    _apply_script(_FORWARD_SQL)

    with get_db_connection(operation="integration.citas.forward_verify") as conn:
        with conn.cursor() as cur:
            for columna in _COLUMNAS_NUEVAS:
                assert _columna_existe(cur, "citas", columna)
            assert _es_not_null(cur, "citas", "fecha_hora_fin")
            assert _es_not_null(cur, "citas", "id_asesor")
            assert _es_not_null(cur, "citas", "updated_at")
            assert _columna_existe(cur, "asesores", "atiende_reuniones")

            assert _constraint_existe(cur, "citas_fecha_hora_fin_gt_inicio_chk")
            assert _constraint_existe(cur, "citas_estado_cita_check")
            assert _constraint_existe(cur, "citas_responsable_no_superposicion_excl")
            assert _index_existe(cur, "citas_one_agendada_per_lead_uq")
            assert _index_existe(cur, "citas_fecha_hora_idx")

            # REVOKE ALL FROM PUBLIC aplicado. El grant exacto a tpi_app (SELECT, INSERT,
            # UPDATE, sin DELETE) lo fija la prueba de texto
            # tests/unit/test_agenda_migration_scripts.py; aqui no se comprueba el conjunto
            # exacto de tpi_app porque en CI tpi_app es el propietario de tpi.citas (y por
            # tanto acumula todos los privilegios de propietario).
            assert _public_tiene_privilegio_citas(cur) is False
        conn.commit()


def test_rollback_migration_revierte_sin_borrar_tabla() -> None:
    _vaciar_citas()
    _apply_script(_ROLLBACK_SQL)
    try:
        with get_db_connection(operation="integration.citas.rollback_verify") as conn:
            with conn.cursor() as cur:
                for columna in _COLUMNAS_NUEVAS:
                    assert _columna_existe(cur, "citas", columna) is False
                assert _es_not_null(cur, "citas", "id_asesor") is False
                assert _columna_existe(cur, "asesores", "atiende_reuniones") is False

                assert _constraint_existe(cur, "citas_fecha_hora_fin_gt_inicio_chk") is False
                assert _constraint_existe(cur, "citas_estado_cita_check") is False
                assert _constraint_existe(cur, "citas_responsable_no_superposicion_excl") is False
                assert _index_existe(cur, "citas_one_agendada_per_lead_uq") is False
                assert _index_existe(cur, "citas_fecha_hora_idx") is False

                # La tabla sigue existiendo.
                cur.execute("SELECT to_regclass('tpi.citas') AS reg")
                assert cur.fetchone()["reg"] is not None
            conn.commit()
    finally:
        # Dejar el esquema en su forma final para el resto de las pruebas.
        _apply_script(_FORWARD_SQL)


def test_dos_agendadas_del_mismo_responsable_que_se_pisan_se_rechazan() -> None:
    nombre = uuid4().hex[:8]
    with get_db_connection(operation="integration.citas.superposicion") as conn:
        with conn.cursor() as cur:
            id_asesor = _make_asesor(cur, nombre)
            id_lead1 = _make_lead(cur, uuid4().hex[:11])
            id_lead2 = _make_lead(cur, uuid4().hex[:11])
            _insertar_cita(
                cur, id_lead=id_lead1, id_asesor=id_asesor, inicio=_hora(10, 0), fin=_hora(10, 30)
            )
            with pytest.raises(ExclusionViolation):
                _insertar_cita(
                    cur,
                    id_lead=id_lead2,
                    id_asesor=id_asesor,
                    inicio=_hora(10, 15),
                    fin=_hora(10, 45),
                )


def test_dos_agendadas_que_no_se_pisan_se_aceptan() -> None:
    nombre = uuid4().hex[:8]
    with get_db_connection(operation="integration.citas.sin_superposicion") as conn:
        with conn.cursor() as cur:
            id_asesor = _make_asesor(cur, nombre)
            id_lead1 = _make_lead(cur, uuid4().hex[:11])
            id_lead2 = _make_lead(cur, uuid4().hex[:11])
            _insertar_cita(
                cur, id_lead=id_lead1, id_asesor=id_asesor, inicio=_hora(10, 0), fin=_hora(10, 30)
            )
            # Una justo despues de la otra (fin == inicio de la siguiente) no se pisa.
            _insertar_cita(
                cur,
                id_lead=id_lead2,
                id_asesor=id_asesor,
                inicio=_hora(10, 30),
                fin=_hora(11, 0),
            )


def test_una_cancelada_o_realizada_no_bloquea_el_horario() -> None:
    nombre = uuid4().hex[:8]
    with get_db_connection(operation="integration.citas.no_bloquea") as conn:
        with conn.cursor() as cur:
            id_asesor = _make_asesor(cur, nombre)
            id_lead1 = _make_lead(cur, uuid4().hex[:11])
            id_lead2 = _make_lead(cur, uuid4().hex[:11])
            id_lead3 = _make_lead(cur, uuid4().hex[:11])
            _insertar_cita(
                cur, id_lead=id_lead1, id_asesor=id_asesor, inicio=_hora(10, 0), fin=_hora(10, 30)
            )
            _insertar_cita(
                cur,
                id_lead=id_lead2,
                id_asesor=id_asesor,
                inicio=_hora(10, 0),
                fin=_hora(10, 30),
                estado="cancelada",
            )
            _insertar_cita(
                cur,
                id_lead=id_lead3,
                id_asesor=id_asesor,
                inicio=_hora(10, 0),
                fin=_hora(10, 30),
                estado="realizada",
            )


def test_un_lead_no_admite_dos_agendadas() -> None:
    nombre = uuid4().hex[:8]
    with get_db_connection(operation="integration.citas.unica_por_lead") as conn:
        with conn.cursor() as cur:
            id_asesor = _make_asesor(cur, nombre)
            id_lead = _make_lead(cur, uuid4().hex[:11])
            _insertar_cita(
                cur, id_lead=id_lead, id_asesor=id_asesor, inicio=_hora(10, 0), fin=_hora(10, 30)
            )
            with pytest.raises(UniqueViolation):
                _insertar_cita(
                    cur,
                    id_lead=id_lead,
                    id_asesor=id_asesor,
                    inicio=_hora(14, 0),
                    fin=_hora(14, 30),
                )


def test_estado_cita_invalido_se_rechaza() -> None:
    nombre = uuid4().hex[:8]
    with get_db_connection(operation="integration.citas.estado_invalido") as conn:
        with conn.cursor() as cur:
            id_asesor = _make_asesor(cur, nombre)
            id_lead = _make_lead(cur, uuid4().hex[:11])
            with pytest.raises(CheckViolation):
                _insertar_cita(
                    cur,
                    id_lead=id_lead,
                    id_asesor=id_asesor,
                    inicio=_hora(10, 0),
                    fin=_hora(10, 30),
                    estado="borrador",
                )


def test_fecha_hora_fin_anterior_al_inicio_se_rechaza() -> None:
    nombre = uuid4().hex[:8]
    with get_db_connection(operation="integration.citas.fin_anterior") as conn:
        with conn.cursor() as cur:
            id_asesor = _make_asesor(cur, nombre)
            id_lead = _make_lead(cur, uuid4().hex[:11])
            with pytest.raises(CheckViolation):
                _insertar_cita(
                    cur,
                    id_lead=id_lead,
                    id_asesor=id_asesor,
                    inicio=_hora(10, 30),
                    fin=_hora(10, 0),
                )
