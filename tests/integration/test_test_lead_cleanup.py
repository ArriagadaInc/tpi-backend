"""PostgreSQL integration tests for DEV test-lead cleanup semantics."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.config import Settings
from app.database.connection import get_db_connection
from app.models import ConsentimientosData, PersonaData, RegistrarSolicitudRequest, SolicitudData
from app.services.solicitud_service import SolicitudService

pytestmark = pytest.mark.integration


def cleanup_service() -> SolicitudService:
    settings = Settings(_env_file=None, APP_ENV="aws-dev", DEV_DELETE_ENABLED="true")
    return SolicitudService(settings=settings)


def build_request(service: SolicitudService, rut: str) -> RegistrarSolicitudRequest:
    return RegistrarSolicitudRequest(
        persona=PersonaData(
            rut=rut,
            nombre_completo="Lead Ficticio H2.3",
            email="lead.ficticio@example.test",
            telefono="+56911112222",
            fecha_nacimiento=date(1990, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=UUID(str(service.get_catalogo_genero()[0]["id"])),
            estado_civil_id=UUID(str(service.get_catalogo_estado_civil()[0]["id"])),
            afp_id=UUID(str(service.get_catalogo_afp()[0]["id"])),
            saldo_afp=Decimal("100000.00"),
            comentarios="Lead ficticio de integracion H2.3",
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )


def build_test_rut() -> str:
    """Generate a unique, checksum-valid synthetic Chilean RUT for integration tests."""
    body = str(10_000_000 + uuid4().int % 80_000_000)
    total = sum(int(digit) * (2 + index % 6) for index, digit in enumerate(reversed(body)))
    verifier = 11 - total % 11
    digit = "0" if verifier == 11 else "K" if verifier == 10 else str(verifier)
    return f"{body}-{digit}"


def test_cleanup_deletes_lead_and_consent_but_retains_exclusive_person() -> None:
    service = cleanup_service()
    rut = build_test_rut()
    response = service.registrar_solicitud(build_request(service, rut))

    try:
        result = service.delete_test_lead(response.id_lead)

        assert result.status == "deleted"
        assert service.get_solicitud_detalle(response.id_lead) is None
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS total FROM tpi.consentimientos WHERE id_lead = %s",
                    (str(response.id_lead),),
                )
                assert cur.fetchone()["total"] == 0
                cur.execute(
                    "SELECT 1 FROM tpi.personas WHERE id_persona = %s",
                    (str(response.id_persona),),
                )
                assert cur.fetchone() is not None
    finally:
        _cleanup_person(response.id_persona)


def test_cleanup_keeps_shared_person_and_second_lead() -> None:
    service = cleanup_service()
    rut = build_test_rut()
    first = service.registrar_solicitud(build_request(service, rut))
    second = service.registrar_solicitud(build_request(service, rut))

    try:
        result = service.delete_test_lead(first.id_lead)

        assert result.status == "deleted"
        assert service.get_solicitud_detalle(first.id_lead) is None
        assert service.get_solicitud_detalle(second.id_lead) is not None
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM tpi.personas WHERE id_persona = %s",
                    (str(first.id_persona),),
                )
                assert cur.fetchone() is not None
    finally:
        service.delete_test_lead(second.id_lead)
        _cleanup_person(first.id_persona)


def test_cleanup_rolls_back_when_operational_fk_blocks_lead_deletion() -> None:
    service = cleanup_service()
    rut = build_test_rut()
    response = service.registrar_solicitud(build_request(service, rut))

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO tpi.auditoria (id_persona, id_lead) VALUES (%s, %s)",
                    (str(response.id_persona), str(response.id_lead)),
                )
            conn.commit()

        result = service.delete_test_lead(response.id_lead)

        assert result.status == "blocked"
        assert service.get_solicitud_detalle(response.id_lead) is not None
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS total FROM tpi.consentimientos WHERE id_lead = %s",
                    (str(response.id_lead),),
                )
                assert cur.fetchone()["total"] == 1
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM tpi.auditoria WHERE id_lead = %s", (str(response.id_lead),)
                )
            conn.commit()
        service.delete_test_lead(response.id_lead)
        _cleanup_person(response.id_persona)


def _cleanup_person(id_persona: UUID) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tpi.consentimientos WHERE id_persona = %s", (str(id_persona),))
            cur.execute("DELETE FROM tpi.leads WHERE id_persona = %s", (str(id_persona),))
            cur.execute("DELETE FROM tpi.personas WHERE id_persona = %s", (str(id_persona),))
        conn.commit()
