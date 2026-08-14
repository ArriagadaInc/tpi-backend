"""Integration tests for database connectivity and transaction behavior."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.database.connection import get_db_connection
from app.database.healthcheck import check_database_connection, full_health_check
from app.models.solicitud import (
    ConsentimientosData,
    PersonaData,
    RegistrarSolicitudRequest,
    SolicitudData,
)
from app.services.solicitud_service import SolicitudService
from app.validators.rut import _calculate_dv


@pytest.fixture(scope="session", autouse=True)
def verify_database() -> None:
    health = full_health_check()
    if not health.get("all_ready"):
        pytest.skip("Base de datos no disponible para tests de integracion")


pytestmark = pytest.mark.integration


def build_test_rut(seed: int) -> str:
    return f"{seed}-{_calculate_dv(seed)}"


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
                cur.execute("DELETE FROM tpi.consentimientos WHERE id_lead = %s", (lead_id,))
                cur.execute("DELETE FROM tpi.leads WHERE id_lead = %s", (lead_id,))

            for persona_id in tracked["persona_ids"]:
                cur.execute("DELETE FROM tpi.consentimientos WHERE id_persona = %s", (persona_id,))
                cur.execute("DELETE FROM tpi.personas WHERE id_persona = %s", (persona_id,))

            for rut in tracked["ruts"]:
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
            assert lead_row["estado_lead"] == "pendiente"
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
                        "pendiente",
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
