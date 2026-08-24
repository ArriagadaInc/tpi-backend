"""Unit and contract coverage for the public FastAPI adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api import create_api_app
from app.api.abuse import resolve_client_ip
from app.api.fingerprint import build_payload_fingerprint
from app.api.schemas import PublicLeadCreateRequest
from app.config import Settings
from app.models import IdempotencyConflictError, IdempotentSolicitudResult, SolicitudResponse

CATALOG_ID = UUID("11111111-1111-1111-1111-111111111111")
LEAD_ID = UUID("22222222-2222-2222-2222-222222222222")
PERSON_ID = UUID("33333333-3333-3333-3333-333333333333")


def valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "rut": "12345678-5",
        "nombre_completo": "Persona Ficticia",
        "email": "persona@example.test",
        "telefono": "+56911112222",
        "fecha_nacimiento": "1990-01-01",
        "genero_id": str(CATALOG_ID),
        "estado_civil_id": str(CATALOG_ID),
        "afp_id": str(CATALOG_ID),
        "saldo_afp": 1000000,
        "comentarios": "Comentario de prueba",
        "consentimientos": {
            "acepta_terminos": True,
            "acepta_politica_privacidad": True,
            "finalidad_contacto": True,
        },
        "honeypot": "",
    }
    payload.update(overrides)
    return payload


class FakeSolicitudService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def get_catalogo_genero(self) -> list[dict[str, object]]:
        return [{"id": CATALOG_ID, "nombre": "Femenino"}]

    def get_catalogo_estado_civil(self) -> list[dict[str, object]]:
        return [{"id": CATALOG_ID, "nombre": "Soltero/a"}]

    def get_catalogo_afp(self) -> list[dict[str, object]]:
        return [{"id": CATALOG_ID, "nombre": "Habitat"}]

    def registrar_solicitud_idempotente(self, request, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append({"request": request, **kwargs})
        if self.error:
            raise self.error
        return IdempotentSolicitudResult(
            lead_id=LEAD_ID,
            created=True,
            response=SolicitudResponse(
                id_lead=LEAD_ID,
                id_persona=PERSON_ID,
                rut="12345678-5",
                nombre_completo="Persona Ficticia",
                fecha_creacion=datetime.now(UTC),
                estado_lead="nuevo",
                mensaje="Solicitud registrada exitosamente",
            ),
        )


def build_client(
    service: FakeSolicitudService | None = None,
    **settings_overrides: object,
) -> tuple[TestClient, FakeSolicitudService]:
    fake_service = service or FakeSolicitudService()
    settings = Settings(
        _env_file=None,
        APP_ENV="testing",
        API_IDEMPOTENCY_HMAC_SECRET="unit-test-hmac-secret",
        **settings_overrides,
    )
    app = create_api_app(settings=settings, service_factory=lambda: fake_service)  # type: ignore[arg-type]
    return TestClient(app), fake_service


def post_lead(client: TestClient, payload: dict[str, object] | None = None, **headers: str):
    request_headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": str(uuid4()),
        **headers,
    }
    return client.post("/api/v1/leads", json=payload or valid_payload(), headers=request_headers)


def test_public_dto_maps_explicitly_to_shared_application_contract() -> None:
    public_request = PublicLeadCreateRequest.model_validate(valid_payload())

    mapped = public_request.to_application_request()

    assert mapped.persona.rut == "12345678-5"
    assert mapped.solicitud.genero_id == CATALOG_ID
    assert mapped.consentimientos.finalidad_contacto is True


def test_fingerprint_is_stable_and_does_not_include_honeypot() -> None:
    first = PublicLeadCreateRequest.model_validate(valid_payload(honeypot=""))
    second = PublicLeadCreateRequest.model_validate(valid_payload(honeypot="bot-value"))

    assert build_payload_fingerprint(first, "key") == build_payload_fingerprint(second, "key")
    assert "Persona Ficticia" not in build_payload_fingerprint(first, "key")


def test_public_api_fails_closed_without_its_dedicated_hmac_secret() -> None:
    settings = Settings(
        _env_file=None,
        APP_ENV="testing",
        API_IDEMPOTENCY_HMAC_SECRET="",
    )

    with pytest.raises(ValueError, match="API_IDEMPOTENCY_HMAC_SECRET"):
        create_api_app(settings=settings)


def _request_with_client_ip(client_ip: str, forwarded_for: str | None = None) -> Request:
    headers = [] if forwarded_for is None else [(b"x-forwarded-for", forwarded_for.encode())]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/leads",
            "headers": headers,
            "client": (client_ip, 12345),
            "server": ("testserver", 80),
        }
    )


def test_untrusted_direct_client_cannot_spoof_forwarded_for() -> None:
    request = _request_with_client_ip("198.51.100.18", "203.0.113.99")

    assert resolve_client_ip(request, "10.0.0.0/8") == "198.51.100.18"


def test_trusted_proxy_forwards_the_original_client_ip() -> None:
    request = _request_with_client_ip("10.0.0.12", "203.0.113.99, 10.0.0.12")

    assert resolve_client_ip(request, "10.0.0.0/8") == "203.0.113.99"


def test_catalogs_contract_returns_only_backend_values() -> None:
    client, _ = build_client()

    response = client.get("/api/v1/catalogs")

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "1.0",
        "generos": [{"id": str(CATALOG_ID), "nombre": "Femenino"}],
        "estados_civiles": [{"id": str(CATALOG_ID), "nombre": "Soltero/a"}],
        "afps": [{"id": str(CATALOG_ID), "nombre": "Habitat"}],
    }
    assert response.headers["x-request-id"]


def test_valid_public_lead_calls_service_once_and_returns_contract() -> None:
    client, service = build_client()

    response = post_lead(client)

    assert response.status_code == 201
    assert response.json()["lead_id"] == str(LEAD_ID)
    assert UUID(response.json()["request_id"])
    assert len(service.calls) == 1
    assert service.calls[0]["request"].persona.email == "persona@example.test"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    "payload",
    [
        valid_payload(saldo_afp=None),
        valid_payload(
            consentimientos={
                "acepta_terminos": False,
                "acepta_politica_privacidad": True,
                "finalidad_contacto": True,
            }
        ),
        valid_payload(genero_id="not-a-uuid"),
    ],
)
def test_invalid_public_payload_is_rejected_before_the_service(payload: dict[str, object]) -> None:
    client, service = build_client()

    response = post_lead(client, payload)

    assert response.status_code == 422
    assert response.json() == {"detail": "Los datos enviados no son validos."}
    assert not service.calls


def test_missing_or_invalid_idempotency_key_is_a_safe_400() -> None:
    client, _ = build_client()

    missing = client.post(
        "/api/v1/leads", json=valid_payload(), headers={"Content-Type": "application/json"}
    )
    invalid = post_lead(client, **{"Idempotency-Key": "not-a-uuid"})

    assert missing.status_code == 400
    assert invalid.status_code == 400


def test_wrong_content_type_and_oversized_body_are_rejected() -> None:
    client, _ = build_client(API_MAX_REQUEST_BYTES=20)

    unsupported = client.post(
        "/api/v1/leads", content="{}", headers={"Idempotency-Key": str(uuid4())}
    )
    oversized = post_lead(client)

    assert unsupported.status_code == 415
    assert oversized.status_code == 413


def test_reused_key_with_different_payload_returns_409() -> None:
    client, _ = build_client(FakeSolicitudService(error=IdempotencyConflictError("different")))

    response = post_lead(client)

    assert response.status_code == 409
    assert "different" not in response.text


def test_honeypot_does_not_persist_or_disclose_detection() -> None:
    client, service = build_client()

    response = post_lead(client, valid_payload(honeypot="filled"))

    assert response.status_code == 201
    assert not service.calls
    assert "bot" not in response.text.lower()


def test_rate_limit_returns_429_without_personal_data() -> None:
    client, _ = build_client(API_RATE_LIMIT_REQUESTS=1)

    assert post_lead(client).status_code == 201
    response = post_lead(client)

    assert response.status_code == 429
    assert "Persona Ficticia" not in response.text


def test_service_failure_returns_a_safe_500() -> None:
    client, _ = build_client(
        FakeSolicitudService(error=RuntimeError("password=secret email@example.test"))
    )

    response = post_lead(client)

    assert response.status_code == 500
    assert "secret" not in response.text
    assert "email@example.test" not in response.text
