"""Integration tests for CRM lead board queries."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from app.database.healthcheck import full_health_check
from app.models.crm_states import CRM_STATE_CONTRACT
from app.models.solicitud import (
    ConsentimientosData,
    PersonaData,
    RegistrarSolicitudRequest,
    SolicitudData,
)
from app.services.solicitud_service import SolicitudService

pytestmark = pytest.mark.integration

CRM_TZ = ZoneInfo("America/Santiago")


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
            nombre_completo="CRM Test",
            email="crm.lite.test@example.com",
            telefono="+56911112222",
            fecha_nacimiento=date(1990, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=genero_id,
            estado_civil_id=estado_civil_id,
            afp_id=afp_id,
            saldo_afp=Decimal("2500000"),
            comentarios="Lead de prueba para CRM",
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
        assert lead["nombre_completo"] == "CRM Test"
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
            nombre_completo="CRM Filter",
            email="crm.lite.filter@example.com",
            telefono="+56933334444",
            fecha_nacimiento=date(1991, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=genero_id,
            estado_civil_id=estado_civil_id,
            afp_id=afp_id,
            saldo_afp=Decimal("3100000"),
            comentarios="Filtro combinado CRM",
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )

    response = service.registrar_solicitud(request)
    try:
        by_name = service.get_crm_bandeja(page=1, page_size=10, masked=False, search="CRM Filter")
        assert by_name["total"] == 1

        lead = by_name["solicitudes"][0]
        lead_date = lead["created_at"].astimezone(CRM_TZ).date()

        combined = service.get_crm_bandeja(
            page=1,
            page_size=10,
            masked=False,
            search=rut,
            estado_lead="nuevo",
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


def test_crm_board_date_filters_use_santiago_day_boundary(service):
    afp_id = UUID(str(service.get_catalogo_afp()[0]["id"]))
    genero_id = UUID(str(service.get_catalogo_genero()[0]["id"]))
    estado_civil_id = UUID(str(service.get_catalogo_estado_civil()[0]["id"]))
    rut = "20987654-4"

    request = RegistrarSolicitudRequest(
        persona=PersonaData(
            rut=rut,
            nombre_completo="CRM TZ Boundary",
            email="crm.lite.tz.boundary@example.com",
            telefono="+56944445555",
            fecha_nacimiento=date(1991, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=genero_id,
            estado_civil_id=estado_civil_id,
            afp_id=afp_id,
            saldo_afp=Decimal("3200000"),
            comentarios="Filtro de fecha en borde UTC/Santiago",
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )

    response = service.registrar_solicitud(request)
    try:
        lead = service.get_solicitud_detalle(response.id_lead)
        assert lead is not None

        created_at_utc = datetime(2026, 8, 22, 0, 30, tzinfo=UTC)
        created_at_santiago = created_at_utc.astimezone(CRM_TZ)
        assert created_at_santiago.date().isoformat() == "2026-08-21"

        from app.database.connection import get_db_connection

        with get_db_connection(operation="test_crm_lite_board_timezone_boundary") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tpi.leads
                       SET created_at = %s
                     WHERE id_lead = %s
                    """,
                    (created_at_utc, str(response.id_lead)),
                )
            conn.commit()

        boundary_day = created_at_santiago.date()
        included = service.get_crm_bandeja(
            page=1,
            page_size=10,
            masked=False,
            search=rut,
            estado_lead="nuevo",
            afp_id=afp_id,
            date_from=boundary_day,
            date_to=boundary_day,
        )

        assert included["total"] == 1
        assert included["solicitudes"][0]["id_lead"] == response.id_lead

        excluded = service.get_crm_bandeja(
            page=1,
            page_size=10,
            masked=False,
            search=rut,
            estado_lead="nuevo",
            afp_id=afp_id,
            date_from=boundary_day + timedelta(days=1),
            date_to=boundary_day + timedelta(days=1),
        )
        assert excluded["total"] == 0
    finally:
        from app.database.connection import get_db_connection

        with get_db_connection(operation="test_crm_lite_board_timezone_cleanup") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM tpi.consentimientos WHERE id_lead = %s",
                    (str(response.id_lead),),
                )
                cur.execute("DELETE FROM tpi.leads WHERE id_lead = %s", (str(response.id_lead),))
            conn.commit()


def test_crm_board_computes_edad_at_the_boundaries(service):
    """CRM-UI-1 AC-3(a): la edad sale en años cumplidos en los bordes.

    Cumpleaños hoy -> edad exacta; cumpleaños mañana -> un año menos; sin fecha
    de nacimiento -> NULL. Las fechas se derivan del ``CURRENT_DATE`` de la propia
    base de datos, de modo que el caso de borde no depende de la zona horaria.
    """
    from app.database.connection import get_db_connection

    with get_db_connection(operation="test_edad_today") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT CURRENT_DATE AS today")
            today = cur.fetchone()["today"]

    def years_ago(base: date, years: int) -> date:
        try:
            return base.replace(year=base.year - years)
        except ValueError:
            # 29 de febrero -> 28 de febrero del año objetivo.
            return base.replace(year=base.year - years, day=28)

    birthday_today = years_ago(today, 64)
    birthday_tomorrow = birthday_today + timedelta(days=1)

    afp_id = UUID(str(service.get_catalogo_afp()[0]["id"]))
    genero_id = UUID(str(service.get_catalogo_genero()[0]["id"]))
    estado_civil_id = UUID(str(service.get_catalogo_estado_civil()[0]["id"]))

    def registrar(rut: str, nacimiento: date) -> str:
        request = RegistrarSolicitudRequest(
            persona=PersonaData(
                rut=rut,
                nombre_completo=f"CRM Edad {rut}",
                email=f"edad.{rut}@example.com",
                telefono="+56911112222",
                fecha_nacimiento=nacimiento,
            ),
            solicitud=SolicitudData(
                genero_id=genero_id,
                estado_civil_id=estado_civil_id,
                afp_id=afp_id,
                saldo_afp=Decimal("2500000"),
                comentarios="Borde de edad",
            ),
            consentimientos=ConsentimientosData(
                acepta_terminos=True,
                acepta_politica_privacidad=True,
                finalidad_contacto=True,
            ),
        )
        return str(service.registrar_solicitud(request).id_lead)

    ids: list[str] = []
    try:
        ids.append(registrar("20990001-1", birthday_today))
        ids.append(registrar("20990002-2", birthday_tomorrow))
        ids.append(registrar("20990003-3", date(1990, 1, 1)))

        # El tercer lead queda sin fecha de nacimiento (legacy).
        with get_db_connection(operation="test_edad_null_birthdate") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tpi.personas p
                       SET fecha_nacimiento = NULL
                     WHERE p.id_persona = (
                           SELECT l.id_persona FROM tpi.leads l WHERE l.id_lead = %s
                       )
                    """,
                    (ids[2],),
                )
            conn.commit()

        board = service.get_crm_bandeja(page=1, page_size=20, masked=False)
        by_lead = {row["id_lead"]: row for row in board["solicitudes"]}

        assert by_lead[ids[0]]["edad"] == 64
        assert by_lead[ids[1]]["edad"] == 63
        assert by_lead[ids[2]]["edad"] is None
    finally:
        with get_db_connection(operation="test_edad_cleanup") as conn:
            with conn.cursor() as cur:
                for id_lead in ids:
                    cur.execute("DELETE FROM tpi.consentimientos WHERE id_lead = %s", (id_lead,))
                    cur.execute("DELETE FROM tpi.leads WHERE id_lead = %s", (id_lead,))
            conn.commit()


def test_crm_estado_options_are_present_and_non_empty(service):
    afp_id = UUID(str(service.get_catalogo_afp()[0]["id"]))
    genero_id = UUID(str(service.get_catalogo_genero()[0]["id"]))
    estado_civil_id = UUID(str(service.get_catalogo_estado_civil()[0]["id"]))
    rut = "20999999-9"

    request = RegistrarSolicitudRequest(
        persona=PersonaData(
            rut=rut,
            nombre_completo="CRM Estado Test",
            email="crm.lite.estado@example.com",
            telefono="+56999998888",
            fecha_nacimiento=date(1992, 2, 2),
        ),
        solicitud=SolicitudData(
            genero_id=genero_id,
            estado_civil_id=estado_civil_id,
            afp_id=afp_id,
            saldo_afp=Decimal("1500000"),
            comentarios="Lead de prueba para estados CRM",
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )

    response = service.registrar_solicitud(request)
    try:
        lead = service.get_solicitud_detalle(response.id_lead)
        assert lead is not None
        assert lead["estado_lead"] == "nuevo"

        states = service.get_crm_estado_lead_options()

        assert states
        assert all(state == state.strip().lower() for state in states)
        assert states == list(CRM_STATE_CONTRACT)
    finally:
        from app.database.connection import get_db_connection

        with get_db_connection(operation="test_crm_estado_options_cleanup") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM tpi.consentimientos WHERE id_lead = %s",
                    (str(response.id_lead),),
                )
                cur.execute("DELETE FROM tpi.leads WHERE id_lead = %s", (str(response.id_lead),))
            conn.commit()
