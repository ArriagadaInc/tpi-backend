"""Unit tests for safe post-commit lead notifications."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID

import pytest

from app.config import Settings
from app.models import ConsentimientosData, PersonaData, RegistrarSolicitudRequest, SolicitudData
from app.models.solicitud import SolicitudResponse
from app.notifications import (
    LeadCreatedEvent,
    PublishResult,
    SnsLeadEventPublisher,
    build_lead_event_publisher,
)
from app.notifications.publisher import MisconfiguredLeadEventPublisher
from app.notifications.sns import format_email_notification, format_sms_notification
from app.services.solicitud_service import SolicitudService

LEAD_ID = UUID("11111111-1111-1111-1111-111111111111")
PERSON_ID = UUID("22222222-2222-2222-2222-222222222222")
CATALOG_ID = UUID("33333333-3333-3333-3333-333333333333")


class FakeRepository:
    """Repository double that models a completed database commit."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.create_calls = 0

    def get_active_genero(self) -> list[dict[str, UUID]]:
        return [{"id": CATALOG_ID}]

    def get_active_estado_civil(self) -> list[dict[str, UUID]]:
        return [{"id": CATALOG_ID}]

    def get_active_afp(self) -> list[dict[str, UUID]]:
        return [{"id": CATALOG_ID}]

    def create_solicitud(self, **_: object) -> SolicitudResponse:
        self.create_calls += 1
        if self.error:
            raise self.error
        return SolicitudResponse(
            id_lead=LEAD_ID,
            id_persona=PERSON_ID,
            rut="12345678-5",
            nombre_completo="Persona Ficticia",
            fecha_creacion=datetime.now(UTC),
            estado_lead="pendiente",
            mensaje="Solicitud registrada exitosamente",
        )


class RecordingPublisher:
    """Small publisher double used to assert post-commit behavior."""

    def __init__(self, result: PublishResult | None = None, error: Exception | None = None) -> None:
        self.result = result or PublishResult("published", "fake", "message-123")
        self.error = error
        self.events: list[LeadCreatedEvent] = []

    def publish(self, event: LeadCreatedEvent) -> PublishResult:
        self.events.append(event)
        if self.error:
            raise self.error
        return self.result


class FakeSnsClient:
    def __init__(
        self, response: dict[str, str] | None = None, error: Exception | None = None
    ) -> None:
        self.response = response or {"MessageId": "sns-message-123"}
        self.error = error
        self.calls: list[dict[str, object]] = []

    def publish(self, **kwargs: object) -> dict[str, str]:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def build_settings(*, enabled: bool = False, topic_arn: str | None = None) -> Settings:
    values: dict[str, object] = {
        "APP_ENV": "testing",
        "LEAD_NOTIFICATIONS_ENABLED": str(enabled).lower(),
    }
    if topic_arn is not None:
        values["LEAD_NOTIFICATION_TOPIC_ARN"] = topic_arn
    return Settings(_env_file=None, **values)


def build_request() -> RegistrarSolicitudRequest:
    return RegistrarSolicitudRequest(
        persona=PersonaData(
            rut="12345678-5",
            nombre_completo="Persona Ficticia Privada",
            email="cliente.ficticio@example.test",
            telefono="+56911112222",
            fecha_nacimiento="1990-01-01",
        ),
        solicitud=SolicitudData(
            genero_id=CATALOG_ID,
            estado_civil_id=CATALOG_ID,
            afp_id=CATALOG_ID,
            saldo_afp=Decimal("987654"),
            comentarios="Comentario privado de prueba",
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )


def fixed_event() -> LeadCreatedEvent:
    return LeadCreatedEvent(
        event_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        lead_id=LEAD_ID,
        occurred_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        environment="aws-dev",
    )


def test_successful_registration_publishes_one_safe_event() -> None:
    publisher = RecordingPublisher()
    service = SolicitudService(FakeRepository(), build_settings(), publisher)  # type: ignore[arg-type]

    response = service.registrar_solicitud(build_request())

    assert response.id_lead == LEAD_ID
    assert len(publisher.events) == 1
    assert publisher.events[0].lead_id == LEAD_ID


def test_database_failure_never_invokes_publisher() -> None:
    publisher = RecordingPublisher()
    service = SolicitudService(FakeRepository(error=RuntimeError("database failed")), build_settings(), publisher)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="No fue posible registrar"):
        service.registrar_solicitud(build_request())

    assert not publisher.events


def test_publisher_failure_keeps_successful_lead_and_hides_internal_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    publisher = RecordingPublisher(error=RuntimeError("token=private customer@example.test"))
    service = SolicitudService(FakeRepository(), build_settings(), publisher)  # type: ignore[arg-type]

    with caplog.at_level(logging.ERROR, logger="app.services.solicitud_service"):
        response = service.registrar_solicitud(build_request())

    assert response.id_lead == LEAD_ID
    assert len(publisher.events) == 1
    assert "event=lead_notification_failed" in caplog.text
    assert "private" not in caplog.text
    assert "customer@example.test" not in caplog.text


def test_disabled_notifications_do_not_create_an_aws_client() -> None:
    with patch("app.notifications.sns.boto3.client") as client_factory:
        publisher = build_lead_event_publisher(build_settings(enabled=False))

    assert publisher.publish(fixed_event()).status == "disabled"
    client_factory.assert_not_called()


def test_enabled_notifications_without_topic_fail_safely_without_aws_call() -> None:
    with patch("app.notifications.sns.boto3.client") as client_factory:
        publisher = build_lead_event_publisher(build_settings(enabled=True))

    assert isinstance(publisher, MisconfiguredLeadEventPublisher)
    assert publisher.publish(fixed_event()).status == "failed"
    client_factory.assert_not_called()


def test_event_uses_independent_uuid_and_timezone_aware_timestamp() -> None:
    event = LeadCreatedEvent.create(lead_id=LEAD_ID, environment="aws-dev")

    assert event.event_id != event.lead_id
    assert event.occurred_at.tzinfo is not None
    assert event.occurred_at.utcoffset() == UTC.utcoffset(event.occurred_at)


def test_event_rejects_naive_timestamp_or_reused_lead_id() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        LeadCreatedEvent(
            event_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            lead_id=LEAD_ID,
            occurred_at=datetime(2026, 8, 15, 12, 0),
            environment="aws-dev",
        )

    with pytest.raises(ValueError, match="independent"):
        LeadCreatedEvent(
            event_id=LEAD_ID,
            lead_id=LEAD_ID,
            occurred_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
            environment="aws-dev",
        )


def test_sns_payload_and_channel_formatters_exclude_request_pii() -> None:
    request = build_request()
    client = FakeSnsClient()
    publisher = SnsLeadEventPublisher(
        "arn:aws:sns:us-east-2:821656895812:tpi-dev-lead-created", client
    )

    result = publisher.publish(fixed_event())

    assert result.status == "published"
    sent_message = json.loads(str(client.calls[0]["Message"]))
    rendered = "\n".join([sent_message["default"], sent_message["email"], sent_message["sms"]])
    for value in (
        request.persona.rut,
        request.persona.nombre_completo,
        request.persona.email,
        request.persona.telefono,
        str(request.solicitud.saldo_afp),
        str(request.solicitud.comentarios),
    ):
        assert value not in rendered

    default_payload = json.loads(sent_message["default"])
    assert set(default_payload) == {
        "environment",
        "event_id",
        "event_type",
        "lead_id",
        "occurred_at",
        "schema_version",
        "source",
    }
    assert "Ambiente: DEV" in format_email_notification(fixed_event())
    assert "TPI DEV" in format_sms_notification(fixed_event())


def test_sns_failure_returns_typed_failed_result() -> None:
    publisher = SnsLeadEventPublisher(
        "arn:aws:sns:us-east-2:821656895812:tpi-dev-lead-created",
        FakeSnsClient(error=RuntimeError("SNS unavailable")),
    )

    assert publisher.publish(fixed_event()) == PublishResult(status="failed", provider="sns")
