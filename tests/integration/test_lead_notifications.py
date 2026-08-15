"""PostgreSQL integration tests for post-commit lead notification semantics."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.database.connection import get_db_connection
from app.models import ConsentimientosData, PersonaData, RegistrarSolicitudRequest, SolicitudData
from app.notifications import LeadCreatedEvent, PublishResult
from app.services.solicitud_service import SolicitudService

pytestmark = pytest.mark.integration


class RecordingPublisher:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.events: list[LeadCreatedEvent] = []

    def publish(self, event: LeadCreatedEvent) -> PublishResult:
        self.events.append(event)
        if self.error:
            raise self.error
        return PublishResult(status="published", provider="fake", message_id="message-123")


def build_request(service: SolicitudService, rut: str) -> RegistrarSolicitudRequest:
    return RegistrarSolicitudRequest(
        persona=PersonaData(
            rut=rut,
            nombre_completo="Lead Ficticio Notificaciones",
            email="lead.notifications@example.test",
            telefono="+56911112222",
            fecha_nacimiento=date(1990, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=UUID(str(service.get_catalogo_genero()[0]["id"])),
            estado_civil_id=UUID(str(service.get_catalogo_estado_civil()[0]["id"])),
            afp_id=UUID(str(service.get_catalogo_afp()[0]["id"])),
            saldo_afp=Decimal("100000"),
            comentarios="Lead ficticio para notificaciones",
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )


def build_test_rut() -> str:
    body = str(10_000_000 + uuid4().int % 80_000_000)
    total = sum(int(digit) * (2 + index % 6) for index, digit in enumerate(reversed(body)))
    verifier = 11 - total % 11
    digit = "0" if verifier == 11 else "K" if verifier == 10 else str(verifier)
    return f"{body}-{digit}"


def test_publisher_receives_event_only_after_lead_is_committed() -> None:
    publisher = RecordingPublisher()
    service = SolicitudService(publisher=publisher)
    response = service.registrar_solicitud(build_request(service, build_test_rut()))

    try:
        assert len(publisher.events) == 1
        assert publisher.events[0].lead_id == response.id_lead
        assert service.get_solicitud_detalle(response.id_lead) is not None
    finally:
        _cleanup(response.id_lead, response.id_persona)


def test_publisher_failure_does_not_roll_back_committed_lead() -> None:
    publisher = RecordingPublisher(error=RuntimeError("SNS unavailable"))
    service = SolicitudService(publisher=publisher)
    response = service.registrar_solicitud(build_request(service, build_test_rut()))

    try:
        assert len(publisher.events) == 1
        assert service.get_solicitud_detalle(response.id_lead) is not None
    finally:
        _cleanup(response.id_lead, response.id_persona)


def _cleanup(id_lead: UUID, id_persona: UUID) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tpi.consentimientos WHERE id_lead = %s", (str(id_lead),))
            cur.execute("DELETE FROM tpi.leads WHERE id_lead = %s", (str(id_lead),))
            cur.execute("DELETE FROM tpi.personas WHERE id_persona = %s", (str(id_persona),))
        conn.commit()
