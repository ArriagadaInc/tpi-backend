"""Integration coverage for public lead idempotency with PostgreSQL."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest

from app.models import (
    ConsentimientosData,
    IdempotencyConflictError,
    PersonaData,
    RegistrarSolicitudRequest,
    SolicitudData,
)
from app.notifications import PublishResult
from app.services import SolicitudService

pytestmark = pytest.mark.integration


def _valid_rut(number: int) -> str:
    body = str(number)
    factors = (2, 3, 4, 5, 6, 7)
    total = sum(
        int(digit) * factors[index % len(factors)] for index, digit in enumerate(reversed(body))
    )
    remainder = 11 - (total % 11)
    verifier = "0" if remainder == 11 else "K" if remainder == 10 else str(remainder)
    return f"{body}-{verifier}"


class RecordingPublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events = []

    def publish(self, event):  # type: ignore[no-untyped-def]
        self.events.append(event)
        if self.fail:
            raise RuntimeError("SNS unavailable")
        return PublishResult(status="published", provider="fake", message_id="message-1")


def _request(service: SolicitudService, rut: str) -> RegistrarSolicitudRequest:
    return RegistrarSolicitudRequest(
        persona=PersonaData(
            rut=rut,
            nombre_completo="Persona API Ficticia",
            email="api.ficticia@example.test",
            telefono="+56911112222",
            fecha_nacimiento=date(1990, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=UUID(str(service.get_catalogo_genero()[0]["id"])),
            estado_civil_id=UUID(str(service.get_catalogo_estado_civil()[0]["id"])),
            afp_id=UUID(str(service.get_catalogo_afp()[0]["id"])),
            saldo_afp=Decimal("1000000"),
            comentarios="Solicitud publica ficticia",
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )


def test_idempotency_persists_one_lead_and_publishes_only_once() -> None:
    publisher = RecordingPublisher()
    service = SolicitudService(publisher=publisher)  # type: ignore[arg-type]
    request = _request(service, _valid_rut(18_000_000 + (uuid4().int % 1_000_000)))
    key = uuid4()

    first = service.registrar_solicitud_idempotente(
        request, idempotency_key=key, payload_fingerprint="a" * 64
    )
    replay = service.registrar_solicitud_idempotente(
        request, idempotency_key=key, payload_fingerprint="a" * 64
    )

    assert first.created is True
    assert replay.created is False
    assert replay.lead_id == first.lead_id
    assert service.get_solicitud_detalle(first.lead_id) is not None
    assert len(publisher.events) == 1


def test_idempotency_rejects_the_same_key_for_a_different_payload() -> None:
    service = SolicitudService(publisher=RecordingPublisher())  # type: ignore[arg-type]
    request = _request(service, _valid_rut(19_000_000 + (uuid4().int % 1_000_000)))
    key = uuid4()
    service.registrar_solicitud_idempotente(
        request, idempotency_key=key, payload_fingerprint="a" * 64
    )

    with pytest.raises(IdempotencyConflictError):
        service.registrar_solicitud_idempotente(
            request, idempotency_key=key, payload_fingerprint="b" * 64
        )


def test_concurrent_requests_with_same_key_create_one_lead_and_publish_once() -> None:
    """The unique reservation must serialize matching concurrent requests."""
    first_publisher = RecordingPublisher()
    second_publisher = RecordingPublisher()
    first_service = SolicitudService(publisher=first_publisher)  # type: ignore[arg-type]
    second_service = SolicitudService(publisher=second_publisher)  # type: ignore[arg-type]
    request = _request(first_service, _valid_rut(21_000_000 + (uuid4().int % 1_000_000)))
    key = uuid4()
    barrier = Barrier(2)

    def submit(service: SolicitudService):  # type: ignore[no-untyped-def]
        barrier.wait()
        return service.registrar_solicitud_idempotente(
            request, idempotency_key=key, payload_fingerprint="d" * 64
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(submit, (first_service, second_service)))

    assert {first.lead_id, second.lead_id} == {first.lead_id}
    assert sorted((first.created, second.created)) == [False, True]
    assert first_service.get_solicitud_detalle(first.lead_id) is not None
    assert len(first_publisher.events) + len(second_publisher.events) == 1


def test_post_commit_notification_failure_keeps_the_idempotent_lead() -> None:
    publisher = RecordingPublisher(fail=True)
    service = SolicitudService(publisher=publisher)  # type: ignore[arg-type]
    request = _request(service, _valid_rut(20_000_000 + (uuid4().int % 1_000_000)))

    result = service.registrar_solicitud_idempotente(
        request, idempotency_key=uuid4(), payload_fingerprint="c" * 64
    )

    assert result.created is True
    assert service.get_solicitud_detalle(result.lead_id) is not None
    assert len(publisher.events) == 1
