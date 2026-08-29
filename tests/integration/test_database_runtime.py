"""Integration tests for database connectivity and transaction behavior."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.auth.models import AuthenticatedUser
from app.config import get_settings
from app.database import DatabaseAppError
from app.database.connection import get_db_connection
from app.database.healthcheck import check_database_connection, full_health_check
from app.models.lead_assignment import (
    LeadAssignmentConflictError,
    LeadAssignmentValidationError,
)
from app.models.solicitud import (
    ConsentimientosData,
    PersonaData,
    RegistrarSolicitudRequest,
    SolicitudData,
)
from app.repositories import solicitud_repository as solicitud_repository_module
from app.services.solicitud_service import SolicitudService
from app.validators.rut import _calculate_dv


@pytest.fixture(scope="session", autouse=True)
def verify_database() -> None:
    health = full_health_check()
    if not health.get("all_ready"):
        pytest.skip("Base de datos no disponible para tests de integracion")


@pytest.fixture(scope="session", autouse=True)
def ensure_assignment_schema_contract() -> None:
    with get_db_connection(operation="integration.assignment_schema_bootstrap") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS asignaciones_one_active_per_lead_uq
                    ON tpi.asignaciones (id_lead)
                    WHERE estado_asignacion = 'activa'
                """)
        conn.commit()


@pytest.fixture(scope="session", autouse=True)
def ensure_assignment_runtime_role() -> None:
    with get_db_connection(operation="integration.assignment_runtime_role_bootstrap") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tpi_assignment_runtime') THEN
                        CREATE ROLE tpi_assignment_runtime
                            LOGIN
                            PASSWORD 'tpi_assignment_runtime_password'
                            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
                    ELSE
                        ALTER ROLE tpi_assignment_runtime
                            LOGIN
                            PASSWORD 'tpi_assignment_runtime_password'
                            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
                    END IF;

                    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), 'tpi_assignment_runtime');
                    EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I', 'tpi', 'tpi_assignment_runtime');
                    EXECUTE format('GRANT SELECT ON TABLE %I.%I TO %I', 'tpi', 'asesores', 'tpi_assignment_runtime');
                    EXECUTE format('GRANT SELECT, INSERT ON TABLE %I.%I TO %I', 'tpi', 'asignaciones', 'tpi_assignment_runtime');
                    EXECUTE format('GRANT INSERT ON TABLE %I.%I TO %I', 'tpi', 'auditoria', 'tpi_assignment_runtime');
                    EXECUTE format('GRANT SELECT, UPDATE ON TABLE %I.%I TO %I', 'tpi', 'leads', 'tpi_assignment_runtime');
                    EXECUTE format(
                        'ALTER ROLE %I IN DATABASE %I SET search_path = %I, public',
                        'tpi_assignment_runtime',
                        current_database(),
                        'tpi'
                    );
                END
                $$;
                """)
        conn.commit()


pytestmark = pytest.mark.integration


def build_test_rut(seed: int) -> str:
    return f"{seed}-{_calculate_dv(seed)}"


def build_assignment_actor() -> AuthenticatedUser:
    return AuthenticatedUser(
        subject="integration-actor-001",
        username="integration.actor",
        display_name="Integration Actor",
        role="executive",
    )


@pytest.fixture
def assignment_runtime_db_connection():
    """Route repository database calls through the restricted runtime role."""

    config = get_settings().database_config.connection_parameters()
    runtime_params = {
        **config,
        "user": "tpi_assignment_runtime",
        "password": "tpi_assignment_runtime_password",
    }
    original_get_db_connection = solicitud_repository_module.get_db_connection

    @contextmanager
    def _runtime_db_connection(operation: str = "database_operation"):
        del operation
        with connect(**runtime_params, row_factory=dict_row) as conn:
            yield conn

    @contextmanager
    def _patched_runtime_connection():
        solicitud_repository_module.get_db_connection = _runtime_db_connection
        try:
            yield
        finally:
            solicitud_repository_module.get_db_connection = original_get_db_connection

    return _patched_runtime_connection


@pytest.fixture
def service() -> SolicitudService:
    return SolicitudService()


@pytest.fixture
def catalog_ids(service: SolicitudService) -> dict[str, UUID]:
    afp_id = UUID(str(service.get_catalogo_afp()[0]["id"]))
    genero_id = UUID(str(service.get_catalogo_genero()[0]["id"]))
    estado_civil_id = UUID(str(service.get_catalogo_estado_civil()[0]["id"]))
    return {
        "afp_id": afp_id,
        "genero_id": genero_id,
        "estado_civil_id": estado_civil_id,
    }


@pytest.fixture
def tracked_entities() -> dict[str, set[str]]:
    tracked: dict[str, set[str]] = {
        "ruts": set(),
        "lead_ids": set(),
        "persona_ids": set(),
    }
    yield tracked

    with get_db_connection(operation="integration.cleanup") as conn:
        with conn.cursor() as cur:
            for lead_id in tracked["lead_ids"]:
                cur.execute("DELETE FROM tpi.auditoria WHERE id_lead = %s", (lead_id,))
                cur.execute("DELETE FROM tpi.asignaciones WHERE id_lead = %s", (lead_id,))
                cur.execute("DELETE FROM tpi.consentimientos WHERE id_lead = %s", (lead_id,))
                cur.execute("DELETE FROM tpi.leads WHERE id_lead = %s", (lead_id,))

            for persona_id in tracked["persona_ids"]:
                cur.execute("DELETE FROM tpi.auditoria WHERE id_persona = %s", (persona_id,))
                cur.execute("DELETE FROM tpi.consentimientos WHERE id_persona = %s", (persona_id,))
                cur.execute("DELETE FROM tpi.personas WHERE id_persona = %s", (persona_id,))

            for rut in tracked["ruts"]:
                cur.execute(
                    "DELETE FROM tpi.auditoria WHERE id_lead IN (SELECT id_lead FROM tpi.leads WHERE id_persona IN (SELECT id_persona FROM tpi.personas WHERE rut = %s))",
                    (rut,),
                )
                cur.execute(
                    "DELETE FROM tpi.asignaciones WHERE id_lead IN (SELECT id_lead FROM tpi.leads WHERE id_persona IN (SELECT id_persona FROM tpi.personas WHERE rut = %s))",
                    (rut,),
                )
                cur.execute(
                    """
                    DELETE FROM tpi.consentimientos
                    WHERE id_persona IN (
                        SELECT id_persona FROM tpi.personas WHERE rut = %s
                    )
                    """,
                    (rut,),
                )
                cur.execute(
                    "DELETE FROM tpi.leads WHERE id_persona IN (SELECT id_persona FROM tpi.personas WHERE rut = %s)",
                    (rut,),
                )
                cur.execute("DELETE FROM tpi.personas WHERE rut = %s", (rut,))

            conn.commit()

        with conn.cursor() as cur:
            for rut in tracked["ruts"]:
                cur.execute("SELECT COUNT(*) AS total FROM tpi.personas WHERE rut = %s", (rut,))
                assert cur.fetchone()["total"] == 0


def test_check_database_connection_reports_effective_user() -> None:
    health = check_database_connection()

    assert health["connected"] is True
    assert health["schema_accessible"] is True
    assert health["leads_accessible"] is True
    assert health["effective_user"]


def test_full_health_check_reports_ready_state() -> None:
    health = full_health_check()

    assert health["all_ready"] is True
    assert health["connected"] is True
    assert health["connection"]["schema_accessible"] is True


def test_insert_read_update_and_cleanup(
    service: SolicitudService,
    catalog_ids: dict[str, UUID],
    tracked_entities: dict[str, set[str]],
) -> None:
    unique_number = 20000000 + int(uuid4().hex[:4], 16)
    rut = build_test_rut(unique_number)
    marker = f"integration-{uuid4().hex[:8]}"
    tracked_entities["ruts"].add(rut)

    request = RegistrarSolicitudRequest(
        persona=PersonaData(
            rut=rut,
            nombre_completo="Integracion Base Datos",
            email=f"{marker}@example.com",
            telefono="+56912345678",
            fecha_nacimiento=date(1990, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=catalog_ids["genero_id"],
            estado_civil_id=catalog_ids["estado_civil_id"],
            afp_id=catalog_ids["afp_id"],
            saldo_afp=Decimal("1500000"),
            comentarios=marker,
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )

    response = service.registrar_solicitud(request)
    tracked_entities["lead_ids"].add(str(response.id_lead))
    tracked_entities["persona_ids"].add(str(response.id_persona))

    detalle = service.get_solicitud_detalle(response.id_lead)
    assert detalle is not None
    assert detalle["rut"] == rut
    assert detalle["comentarios"] == marker

    with get_db_connection(operation="integration.traceability") as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT estado_lead, origen_lead, fuente_actual, fecha_ingreso, created_at
                FROM tpi.leads
                WHERE id_lead = %s
                """,
                (str(response.id_lead),),
            )
            lead_row = cur.fetchone()
            assert lead_row["estado_lead"] == "nuevo"
            assert lead_row["origen_lead"] == "formulario_streamlit"
            assert lead_row["fuente_actual"] == "backoffice"
            assert lead_row["fecha_ingreso"] is not None
            assert lead_row["created_at"] is not None

            updated_comment = f"{marker}-updated"
            cur.execute(
                """
                UPDATE tpi.leads
                SET comentarios = %s
                WHERE id_lead = %s
                RETURNING comentarios
                """,
                (updated_comment, str(response.id_lead)),
            )
            update_row = cur.fetchone()
            conn.commit()

    assert update_row["comentarios"] == f"{marker}-updated"

    refreshed = service.get_solicitud_detalle(response.id_lead)
    assert refreshed is not None
    assert refreshed["comentarios"] == f"{marker}-updated"


def test_assignment_creates_row_updates_state_and_audits(
    service: SolicitudService,
    catalog_ids: dict[str, UUID],
    tracked_entities: dict[str, set[str]],
    assignment_runtime_db_connection,
) -> None:
    asesores = service.get_asesores_disponibles_para_asignacion()
    assert len(asesores) >= 2
    asesor_id = UUID(str(asesores[0]["id_asesor"]))
    marker = f"assignment-{uuid4().hex[:8]}"
    unique_number = 40000000 + int(uuid4().hex[:4], 16)
    rut = build_test_rut(unique_number)
    tracked_entities["ruts"].add(rut)

    request = RegistrarSolicitudRequest(
        persona=PersonaData(
            rut=rut,
            nombre_completo="Assignment Integration",
            email=f"{marker}@example.com",
            telefono="+56912345679",
            fecha_nacimiento=date(1990, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=catalog_ids["genero_id"],
            estado_civil_id=catalog_ids["estado_civil_id"],
            afp_id=catalog_ids["afp_id"],
            saldo_afp=Decimal("1500000"),
            comentarios=marker,
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )

    response = service.registrar_solicitud(request)
    tracked_entities["lead_ids"].add(str(response.id_lead))
    tracked_entities["persona_ids"].add(str(response.id_persona))

    with assignment_runtime_db_connection():
        runtime_service = SolicitudService()
        assigned = runtime_service.assign_lead(
            response.id_lead,
            asesor_id,
            actor=build_assignment_actor(),
        )
    assert assigned is True

    detalle = service.get_solicitud_detalle(response.id_lead)
    assert detalle is not None
    assert detalle["estado_lead"] == "asignado"
    assert str(detalle["id_asesor"]) == str(asesor_id)
    assert detalle["asesor_nombre"] is not None

    with get_db_connection(operation="integration.assignment.verify") as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id_lead, id_asesor, asignado_por, estado_asignacion, regla_asignacion
                FROM tpi.asignaciones
                WHERE id_lead = %s
                ORDER BY fecha_asignacion DESC, id_asignacion DESC
                LIMIT 1
                """,
                (str(response.id_lead),),
            )
            assignment_row = cur.fetchone()
            assert assignment_row is not None
            assert str(assignment_row["id_lead"]) == str(response.id_lead)
            assert str(assignment_row["id_asesor"]) == str(asesor_id)
            assert assignment_row["asignado_por"] == "integration-actor-001"
            assert assignment_row["estado_asignacion"] == "activa"
            assert assignment_row["regla_asignacion"] == "manual"

            cur.execute(
                """
                SELECT accion, tabla_afectada, detalle
                FROM tpi.auditoria
                WHERE id_lead = %s
                ORDER BY fecha_hora DESC
                LIMIT 1
                """,
                (str(response.id_lead),),
            )
            audit_row = cur.fetchone()
            assert audit_row is not None
            assert audit_row["accion"] == "asignacion_lead"
            assert audit_row["tabla_afectada"] == "tpi.asignaciones"
            assert audit_row["detalle"]["id_asesor"] == str(asesor_id)
            assert audit_row["detalle"]["estado_anterior"] == "nuevo"
            assert audit_row["detalle"]["estado_nuevo"] == "asignado"


def test_assignment_rejects_second_active_assignment(
    service: SolicitudService,
    catalog_ids: dict[str, UUID],
    tracked_entities: dict[str, set[str]],
    assignment_runtime_db_connection,
) -> None:
    asesores = service.get_asesores_disponibles_para_asignacion()
    assert len(asesores) >= 2
    asesor_inicial = UUID(str(asesores[0]["id_asesor"]))
    asesor_secundario = UUID(str(asesores[1]["id_asesor"]))
    marker = f"conflict-{uuid4().hex[:8]}"
    unique_number = 41000000 + int(uuid4().hex[:4], 16)
    rut = build_test_rut(unique_number)
    tracked_entities["ruts"].add(rut)

    request = RegistrarSolicitudRequest(
        persona=PersonaData(
            rut=rut,
            nombre_completo="Assignment Conflict Integration",
            email=f"{marker}@example.com",
            telefono="+56912345670",
            fecha_nacimiento=date(1990, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=catalog_ids["genero_id"],
            estado_civil_id=catalog_ids["estado_civil_id"],
            afp_id=catalog_ids["afp_id"],
            saldo_afp=Decimal("1500000"),
            comentarios=marker,
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )

    response = service.registrar_solicitud(request)
    tracked_entities["lead_ids"].add(str(response.id_lead))
    tracked_entities["persona_ids"].add(str(response.id_persona))

    with assignment_runtime_db_connection():
        runtime_service = SolicitudService()
        assert runtime_service.assign_lead(
            response.id_lead,
            asesor_inicial,
            actor=build_assignment_actor(),
        )

    with pytest.raises(LeadAssignmentConflictError):
        with assignment_runtime_db_connection():
            runtime_service = SolicitudService()
            runtime_service.assign_lead(
                response.id_lead,
                asesor_secundario,
                actor=build_assignment_actor(),
            )

    with get_db_connection(operation="integration.assignment.conflict.verify") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS total FROM tpi.asignaciones WHERE id_lead = %s",
                (str(response.id_lead),),
            )
            assert cur.fetchone()["total"] == 1
            cur.execute(
                "SELECT estado_lead FROM tpi.leads WHERE id_lead = %s",
                (str(response.id_lead),),
            )
            assert cur.fetchone()["estado_lead"] == "asignado"


def test_assignment_rejects_invalid_or_inactive_advisor(
    service: SolicitudService,
    catalog_ids: dict[str, UUID],
    tracked_entities: dict[str, set[str]],
    assignment_runtime_db_connection,
) -> None:
    asesores = service.get_asesores_disponibles_para_asignacion()
    assert asesores
    asesor_inicial = UUID(str(asesores[0]["id_asesor"]))
    marker = f"invalid-asesor-{uuid4().hex[:8]}"
    unique_number = 43000000 + int(uuid4().hex[:4], 16)
    rut = build_test_rut(unique_number)
    tracked_entities["ruts"].add(rut)

    request = RegistrarSolicitudRequest(
        persona=PersonaData(
            rut=rut,
            nombre_completo="Assignment Invalid Advisor",
            email=f"{marker}@example.com",
            telefono="+56912345672",
            fecha_nacimiento=date(1990, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=catalog_ids["genero_id"],
            estado_civil_id=catalog_ids["estado_civil_id"],
            afp_id=catalog_ids["afp_id"],
            saldo_afp=Decimal("1500000"),
            comentarios=marker,
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )

    response = service.registrar_solicitud(request)
    tracked_entities["lead_ids"].add(str(response.id_lead))
    tracked_entities["persona_ids"].add(str(response.id_persona))

    with assignment_runtime_db_connection():
        runtime_service = SolicitudService()
        with pytest.raises(LeadAssignmentValidationError, match="asesor"):
            runtime_service.assign_lead(
                response.id_lead,
                UUID("00000000-0000-0000-0000-000000000000"),
                actor=build_assignment_actor(),
            )

    with get_db_connection(operation="integration.assignment.inactive.toggle") as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tpi.asesores
                SET estado_disponibilidad = 'inactivo'
                WHERE id_asesor = %s
                    """,
                (str(asesor_inicial),),
            )
        conn.commit()

    try:
        with assignment_runtime_db_connection():
            runtime_service = SolicitudService()
            with pytest.raises(LeadAssignmentValidationError, match="habilitado"):
                runtime_service.assign_lead(
                    response.id_lead,
                    asesor_inicial,
                    actor=build_assignment_actor(),
                )
    finally:
        with get_db_connection(operation="integration.assignment.inactive.restore") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tpi.asesores
                    SET estado_disponibilidad = 'activo'
                    WHERE id_asesor = %s
                    """,
                    (str(asesor_inicial),),
                )
            conn.commit()


def test_assignment_concurrency_keeps_exactly_one_active_row(
    service: SolicitudService,
    catalog_ids: dict[str, UUID],
    tracked_entities: dict[str, set[str]],
    assignment_runtime_db_connection,
) -> None:
    asesores = service.get_asesores_disponibles_para_asignacion()
    assert len(asesores) >= 2
    asesor_a = UUID(str(asesores[0]["id_asesor"]))
    asesor_b = UUID(str(asesores[1]["id_asesor"]))
    marker = f"concurrency-{uuid4().hex[:8]}"
    unique_number = 44000000 + int(uuid4().hex[:4], 16)
    rut = build_test_rut(unique_number)
    tracked_entities["ruts"].add(rut)

    request = RegistrarSolicitudRequest(
        persona=PersonaData(
            rut=rut,
            nombre_completo="Assignment Concurrency",
            email=f"{marker}@example.com",
            telefono="+56912345673",
            fecha_nacimiento=date(1990, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=catalog_ids["genero_id"],
            estado_civil_id=catalog_ids["estado_civil_id"],
            afp_id=catalog_ids["afp_id"],
            saldo_afp=Decimal("1500000"),
            comentarios=marker,
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )

    response = service.registrar_solicitud(request)
    tracked_entities["lead_ids"].add(str(response.id_lead))
    tracked_entities["persona_ids"].add(str(response.id_persona))

    barrier = Barrier(2)

    def _attempt_assignment(asesor_id: UUID) -> str:
        barrier.wait()
        try:
            with assignment_runtime_db_connection():
                runtime_service = SolicitudService()
                return (
                    "ok"
                    if runtime_service.assign_lead(
                        response.id_lead,
                        asesor_id,
                        actor=build_assignment_actor(),
                    )
                    else "not_found"
                )
        except LeadAssignmentConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(_attempt_assignment, (asesor_a, asesor_b)))

    assert results.count("ok") == 1
    assert results.count("conflict") == 1

    with get_db_connection(operation="integration.assignment.concurrency.verify") as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM tpi.asignaciones
                WHERE id_lead = %s AND estado_asignacion = 'activa'
                """,
                (str(response.id_lead),),
            )
            assert cur.fetchone()["total"] == 1
            cur.execute(
                "SELECT estado_lead FROM tpi.leads WHERE id_lead = %s",
                (str(response.id_lead),),
            )
            assert cur.fetchone()["estado_lead"] == "asignado"


def test_assignment_unique_partial_index_rolls_back_duplicate_active_rows(
    service: SolicitudService,
    catalog_ids: dict[str, UUID],
    tracked_entities: dict[str, set[str]],
) -> None:
    asesores = service.get_asesores_disponibles_para_asignacion()
    assert len(asesores) >= 2
    asesor_inicial = UUID(str(asesores[0]["id_asesor"]))
    asesor_secundario = UUID(str(asesores[1]["id_asesor"]))
    marker = f"rollback-{uuid4().hex[:8]}"
    unique_number = 42000000 + int(uuid4().hex[:4], 16)
    rut = build_test_rut(unique_number)
    tracked_entities["ruts"].add(rut)

    request = RegistrarSolicitudRequest(
        persona=PersonaData(
            rut=rut,
            nombre_completo="Assignment Rollback Integration",
            email=f"{marker}@example.com",
            telefono="+56912345671",
            fecha_nacimiento=date(1990, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=catalog_ids["genero_id"],
            estado_civil_id=catalog_ids["estado_civil_id"],
            afp_id=catalog_ids["afp_id"],
            saldo_afp=Decimal("1500000"),
            comentarios=marker,
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )

    response = service.registrar_solicitud(request)
    tracked_entities["lead_ids"].add(str(response.id_lead))
    tracked_entities["persona_ids"].add(str(response.id_persona))

    with pytest.raises(DatabaseAppError):
        with get_db_connection(operation="integration.assignment.rollback") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tpi.asignaciones
                        (id_lead, id_asesor, asignado_por, regla_asignacion, estado_asignacion, observacion)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(response.id_lead),
                        str(asesor_inicial),
                        "integration-actor-001",
                        "manual",
                        "activa",
                        None,
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO tpi.asignaciones
                        (id_lead, id_asesor, asignado_por, regla_asignacion, estado_asignacion, observacion)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(response.id_lead),
                        str(asesor_secundario),
                        "integration-actor-001",
                        "manual",
                        "activa",
                        None,
                    ),
                )
                conn.commit()

    with get_db_connection(operation="integration.assignment.rollback.verify") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS total FROM tpi.asignaciones WHERE id_lead = %s",
                (str(response.id_lead),),
            )
            assert cur.fetchone()["total"] == 0
            cur.execute(
                "SELECT estado_lead FROM tpi.leads WHERE id_lead = %s",
                (str(response.id_lead),),
            )
            assert cur.fetchone()["estado_lead"] == "nuevo"


def test_assignment_runtime_role_has_exact_minimum_privileges() -> None:
    with get_db_connection(operation="integration.assignment.privileges") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    has_schema_privilege('tpi_assignment_runtime', 'tpi', 'USAGE') AS schema_usage,
                    has_table_privilege('tpi_assignment_runtime', 'tpi.asesores', 'SELECT') AS asesores_select,
                    has_table_privilege('tpi_assignment_runtime', 'tpi.asesores', 'INSERT') AS asesores_insert,
                    has_table_privilege('tpi_assignment_runtime', 'tpi.asesores', 'UPDATE') AS asesores_update,
                    has_table_privilege('tpi_assignment_runtime', 'tpi.asesores', 'DELETE') AS asesores_delete,
                    has_table_privilege('tpi_assignment_runtime', 'tpi.asignaciones', 'SELECT') AS asignaciones_select,
                    has_table_privilege('tpi_assignment_runtime', 'tpi.asignaciones', 'INSERT') AS asignaciones_insert,
                    has_table_privilege('tpi_assignment_runtime', 'tpi.asignaciones', 'UPDATE') AS asignaciones_update,
                    has_table_privilege('tpi_assignment_runtime', 'tpi.asignaciones', 'DELETE') AS asignaciones_delete,
                    has_table_privilege('tpi_assignment_runtime', 'tpi.auditoria', 'INSERT') AS auditoria_insert,
                    has_table_privilege('tpi_assignment_runtime', 'tpi.auditoria', 'SELECT') AS auditoria_select,
                    has_table_privilege('tpi_assignment_runtime', 'tpi.auditoria', 'UPDATE') AS auditoria_update,
                    has_table_privilege('tpi_assignment_runtime', 'tpi.auditoria', 'DELETE') AS auditoria_delete,
                    has_table_privilege('tpi_assignment_runtime', 'tpi.leads', 'SELECT') AS leads_select,
                    has_table_privilege('tpi_assignment_runtime', 'tpi.leads', 'UPDATE') AS leads_update
                """)
            row = cur.fetchone()

    assert row is not None
    assert row["schema_usage"] is True
    assert row["asesores_select"] is True
    assert row["asesores_insert"] is False
    assert row["asesores_update"] is False
    assert row["asesores_delete"] is False
    assert row["asignaciones_select"] is True
    assert row["asignaciones_insert"] is True
    assert row["asignaciones_update"] is False
    assert row["asignaciones_delete"] is False
    assert row["auditoria_insert"] is True
    assert row["auditoria_select"] is False
    assert row["auditoria_update"] is False
    assert row["auditoria_delete"] is False
    assert row["leads_select"] is True
    assert row["leads_update"] is True


def test_transaction_rollback_on_failure_leaves_no_residual_data(
    catalog_ids: dict[str, UUID],
    tracked_entities: dict[str, set[str]],
) -> None:
    unique_number = 30000000 + int(uuid4().hex[:4], 16)
    rut = build_test_rut(unique_number)
    tracked_entities["ruts"].add(rut)
    invalid_afp_id = UUID("00000000-0000-0000-0000-000000000001")

    with pytest.raises(Exception):
        with get_db_connection(operation="integration.rollback") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tpi.personas
                        (rut, nombre_completo, email, telefono, fecha_nacimiento, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id_persona
                    """,
                    (
                        rut,
                        "Rollback Integration",
                        "rollback@example.com",
                        "+56912345678",
                        date(1990, 1, 1),
                        datetime.now(),
                    ),
                )
                persona_row = cur.fetchone()
                tracked_entities["persona_ids"].add(str(persona_row["id_persona"]))

                cur.execute(
                    """
                    INSERT INTO tpi.leads
                        (id_persona, genero_id, estado_civil_id, afp_id, saldo_afp, comentarios,
                         estado_lead, fecha_ingreso, origen_lead, fuente_actual, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(persona_row["id_persona"]),
                        str(catalog_ids["genero_id"]),
                        str(catalog_ids["estado_civil_id"]),
                        str(invalid_afp_id),
                        Decimal("1000"),
                        "force-rollback",
                        "nuevo",
                        datetime.now(),
                        "integration-test",
                        "integration-test",
                        datetime.now(),
                    ),
                )
                conn.commit()

    with get_db_connection(operation="integration.rollback.verify") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM tpi.personas WHERE rut = %s", (rut,))
            assert cur.fetchone()["total"] == 0
