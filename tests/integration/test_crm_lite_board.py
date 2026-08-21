"""Integration tests for CRM Lite lead board queries."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from app.database.healthcheck import full_health_check
from app.models.solicitud import (
    ConsentimientosData,
    PersonaData,
    RegistrarSolicitudRequest,
    SolicitudData,
)
from app.services.solicitud_service import SolicitudService

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session", autouse=True)
def verify_database():
    health = full_health_check()
    if not health.get("all_ready"):
        pytest.skip("Base de datos no disponible para tests de integración")


@pytest.fixture
def service():
    return SolicitudService()


def test_crm_board_searches_newly_created_lead_and_keeps_existing_columns(service):
    afp_id = UUID(str(service.get_catalogo_afp()[0]["id"]))
    genero_id = UUID(str(service.get_catalogo_genero()[0]["id"]))
    estado_civil_id = UUID(str(service.get_catalogo_estado_civil()[0]["id"]))
    rut = "20123456-7"
    request = RegistrarSolicitudRequest(
        persona=PersonaData(
            rut=rut,
            nombre_completo="CRM Lite Test",
            email="crm.lite.test@example.com",
            telefono="+56911112222",
            fecha_nacimiento=date(1990, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=genero_id,
            estado_civil_id=estado_civil_id,
            afp_id=afp_id,
            saldo_afp=Decimal("2500000"),
            comentarios="Lead de prueba para CRM Lite",
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )

    response = service.registrar_solicitud(request)
    try:
        result = service.get_crm_bandeja(page=1, page_size=10, masked=False, search=rut)
        assert result["total"] >= 1
        assert any(row["id_lead"] == response.id_lead for row in result["solicitudes"])
        lead = next(row for row in result["solicitudes"] if row["id_lead"] == response.id_lead)
        assert lead["rut"] == rut
        assert lead["nombre_completo"] == "CRM Lite Test"
        assert "saldo_afp" in lead
        assert "estado_lead" in lead
        assert "created_at" in lead
    finally:
        from app.database.connection import get_db_connection

        with get_db_connection(operation="test_crm_lite_board_cleanup") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM tpi.consentimientos WHERE id_lead = %s",
                    (str(response.id_lead),),
                )
                cur.execute("DELETE FROM tpi.leads WHERE id_lead = %s", (str(response.id_lead),))
            conn.commit()


def test_crm_board_combines_afp_estado_and_date_filters(service):
    afps = service.get_catalogo_afp()
    generos = service.get_catalogo_genero()
    estados = service.get_catalogo_estado_civil()
    assert afps and generos and estados

    afp_id = UUID(str(afps[0]["id"]))
    afp_name = str(afps[0]["nombre"])
    genero_id = UUID(str(generos[0]["id"]))
    estado_civil_id = UUID(str(estados[0]["id"]))
    rut = "20987654-3"

    request = RegistrarSolicitudRequest(
        persona=PersonaData(
            rut=rut,
            nombre_completo="CRM Lite Filter",
            email="crm.lite.filter@example.com",
            telefono="+56933334444",
            fecha_nacimiento=date(1991, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=genero_id,
            estado_civil_id=estado_civil_id,
            afp_id=afp_id,
            saldo_afp=Decimal("3100000"),
            comentarios="Filtro combinado CRM Lite",
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )

    response = service.registrar_solicitud(request)
    try:
        by_name = service.get_crm_bandeja(
            page=1, page_size=10, masked=False, search="CRM Lite Filter"
        )
        assert by_name["total"] == 1

        lead = by_name["solicitudes"][0]
        lead_date = lead["created_at"].date()

        combined = service.get_crm_bandeja(
            page=1,
            page_size=10,
            masked=False,
            search=rut,
            estado_lead="pendiente",
            afp_id=afp_id,
            date_from=lead_date,
            date_to=lead_date,
        )

        assert combined["total"] == 1
        assert combined["solicitudes"][0]["id_lead"] == response.id_lead
        assert combined["solicitudes"][0]["afp"] == afp_name

        empty = service.get_crm_bandeja(
            page=1,
            page_size=10,
            masked=False,
            date_from=lead_date + timedelta(days=1),
            date_to=lead_date + timedelta(days=1),
        )
        assert empty["total"] == 0
        assert empty["solicitudes"] == []
    finally:
        from app.database.connection import get_db_connection

        with get_db_connection(operation="test_crm_lite_board_cleanup") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM tpi.consentimientos WHERE id_lead = %s",
                    (str(response.id_lead),),
                )
                cur.execute("DELETE FROM tpi.leads WHERE id_lead = %s", (str(response.id_lead),))
            conn.commit()
