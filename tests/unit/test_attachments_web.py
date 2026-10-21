"""Pruebas web de la subida, vista, descarga y borrado de adjuntos (AC-4/6/9)."""

from __future__ import annotations

import logging
import re
import struct
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.abuse import InMemoryRateLimiter
from app.attachments.storage import StoredObject
from app.auth.models import AuthenticatedUser, AuthenticationResult, UserRole
from app.config import Settings
from app.services.solicitud_service import SolicitudService
from app.web.main import create_web_app

LEAD_ID = UUID("11111111-1111-1111-1111-111111111111")
ADVISOR_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ATTACH_ID = UUID("22222222-2222-2222-2222-222222222222")


def _png(width: int = 1, height: int = 1) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00"
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + b"\x00\x00\x00\x00"
    iend = struct.pack(">I", 0) + b"IEND" + b"\x00\x00\x00\x00"
    return signature + ihdr + iend


class _FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, StoredObject] = {}
        self.put_calls: list[str] = []
        self.get_calls: list[str] = []
        self.delete_calls: list[str] = []

    def put(self, key: str, body: bytes, *, content_type: str, metadata: dict[str, str]) -> None:
        self.put_calls.append(key)
        self.objects[key] = StoredObject(content=body, content_type=content_type, metadata=metadata)

    def get(self, key: str) -> StoredObject | None:
        self.get_calls.append(key)
        return self.objects.get(key)

    def delete(self, key: str) -> None:
        self.delete_calls.append(key)
        self.objects.pop(key, None)


class _FakeRepo:
    def __init__(self) -> None:
        self.lead: dict[str, Any] = {
            "id_lead": str(LEAD_ID),
            "comentarios": "Solicitud original.",
            "rut": "12.345.678-5",
            "email": "juan@example.com",
            "telefono": "+56 9 1234 5678",
            "nombre_completo": "Juan Perez",
            "created_at": None,
            "afp": "Habitat",
            "saldo_afp": 1000,
            "estado_lead": "nuevo",
        }
        self.comments: list[str] = []
        self.owned = True

    def get_solicitud_by_id(self, id_lead: UUID) -> dict[str, Any] | None:
        return dict(self.lead) if str(id_lead) == str(LEAD_ID) else None

    def append_lead_comment(
        self, id_lead: UUID, fragment: str, *, advisor_scope: UUID | None = None
    ) -> bool:
        if advisor_scope is not None and not self.owned:
            return False
        self.comments.append(fragment)
        self.lead["comentarios"] = f"{self.lead['comentarios']}\n\n{fragment}"
        return True

    def lead_active_assignment_belongs_to(self, id_lead: UUID, id_asesor: UUID) -> bool:
        return self.owned

    def get_active_advisor_by_id(self, id_asesor: UUID) -> dict[str, Any] | None:
        return {"id_asesor": str(id_asesor), "rol": "asesor", "estado_disponibilidad": "activo"}

    def get_crm_estado_lead_options(self) -> list[str]:
        return ["nuevo", "contactado", "cerrado"]

    def get_crm_estado_lead_options_for_update(self) -> list[str]:
        return ["nuevo", "contactado", "cerrado"]

    def get_active_afp(self) -> list[dict[str, Any]]:
        return []

    def get_catalogo_afp(self) -> list[dict[str, Any]]:
        return []

    def get_asesores_disponibles_para_asignacion(self) -> list[dict[str, Any]]:
        return []

    def get_lead_assignment_events(self, id_lead: UUID) -> list[dict[str, Any]]:
        return []

    def get_lead_state_change_events(self, id_lead: UUID) -> list[dict[str, Any]]:
        return []

    def get_lead_simulation_events(self, id_lead: UUID) -> list[dict[str, Any]]:
        return []


class _AuthProvider:
    def __init__(self, role: str, advisor_id: UUID | None = None) -> None:
        self._role = role
        self._advisor_id = advisor_id

    def authenticate(self, username: str, password: str) -> AuthenticationResult:
        return AuthenticationResult(
            status="authenticated",
            user=AuthenticatedUser(
                subject=f"subject-{self._role}",
                username=username,
                display_name=f"User {self._role}",
                role=cast(UserRole, self._role),
                advisor_id=self._advisor_id if self._role == "advisor" else None,
            ),
        )


def _client(
    role: str = "ceo",
    *,
    repo: _FakeRepo | None = None,
    storage: _FakeStorage | None = None,
    audit: list[dict[str, Any]] | None = None,
    advisor_id: UUID | None = None,
    attachments_enabled: bool = True,
) -> tuple[TestClient, _FakeRepo, _FakeStorage, list[dict[str, Any]]]:
    repo = repo or _FakeRepo()
    storage = storage or _FakeStorage()
    audit_events: list[dict[str, Any]] = audit if audit is not None else []

    def audit_writer(**kwargs: Any) -> None:
        audit_events.append(dict(kwargs))

    service = SolicitudService(
        repository=cast(Any, repo),
        settings=Settings(
            APP_ENV="local",
            AUTH_ENABLED=True,
            AUTH_MODE="simple-dev",
            ATTACHMENTS_ENABLED=attachments_enabled,
            ATTACHMENTS_BUCKET="bucket" if attachments_enabled else None,
            WEB_MASK_PII=True,
        ),
        storage=cast(Any, storage),
        attachment_audit=audit_writer,
    )
    app = create_web_app()
    app.state.web_service = service
    app.state.auth_provider = _AuthProvider(role, advisor_id)
    app.state.settings = Settings(
        APP_ENV="local",
        AUTH_ENABLED=True,
        AUTH_MODE="simple-dev",
        ATTACHMENTS_ENABLED=attachments_enabled,
        ATTACHMENTS_BUCKET="bucket" if attachments_enabled else None,
        WEB_MASK_PII=True,
    )
    client = TestClient(app)
    response = client.post(
        "/login", data={"username": f"{role}.local", "password": "x"}, follow_redirects=False
    )
    assert response.status_code == 303
    return client, repo, storage, audit_events


def _csrf(client: TestClient) -> str:
    response = client.get(f"/leads/{LEAD_ID}")
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match is not None
    return match.group(1)


def test_upload_success_appends_note_with_mark_and_audits() -> None:
    client, repo, storage, audit = _client("ceo")
    csrf = _csrf(client)
    response = client.post(
        f"/leads/{LEAD_ID}/comments",
        data={"csrf_token": csrf, "new_comment": "Nota con imagen", "return_to": "/leads"},
        files=[("files", ("foto.png", _png(), "image/png"))],
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert len(storage.put_calls) == 1
    assert storage.put_calls[0].startswith(f"leads/{LEAD_ID}/")
    assert "[adjunto:png:" in repo.comments[-1]
    assert any(event["accion"] == "adjunto_subido" for event in audit)


def test_upload_without_csrf_makes_no_s3_call() -> None:
    client, _, storage, audit = _client("ceo")
    response = client.post(
        f"/leads/{LEAD_ID}/comments",
        data={"csrf_token": "bad", "new_comment": "Nota"},
        files=[("files", ("foto.png", _png(), "image/png"))],
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert storage.put_calls == []
    assert audit == []


def test_upload_by_advisor_on_foreign_lead_makes_no_s3_call() -> None:
    repo = _FakeRepo()
    repo.owned = True
    client, _, storage, audit = _client("advisor", repo=repo, advisor_id=ADVISOR_ID)
    csrf = _csrf(client)  # el asesor ve su cartera y obtiene el token
    repo.owned = False  # ahora el lead es ajeno
    response = client.post(
        f"/leads/{LEAD_ID}/comments",
        data={"csrf_token": csrf, "new_comment": "Nota"},
        files=[("files", ("foto.png", _png(), "image/png"))],
        follow_redirects=False,
    )
    assert response.status_code == 404
    assert storage.put_calls == []
    assert audit == []


def test_upload_with_invalid_content_is_rejected_and_audited() -> None:
    client, _, storage, audit = _client("ceo")
    csrf = _csrf(client)
    response = client.post(
        f"/leads/{LEAD_ID}/comments",
        data={"csrf_token": csrf, "new_comment": "Nota"},
        files=[("files", ("evil.svg", b"<svg></svg>", "image/svg+xml"))],
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert storage.put_calls == []
    assert any(event["accion"] == "adjunto_rechazado" for event in audit)


def test_upload_six_files_is_rejected() -> None:
    client, _, storage, _audit = _client("ceo")
    csrf = _csrf(client)
    files = [("files", (f"f{i}.png", _png(), "image/png")) for i in range(6)]
    response = client.post(
        f"/leads/{LEAD_ID}/comments",
        data={"csrf_token": csrf, "new_comment": "Nota"},
        files=files,
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert storage.put_calls == []


def test_upload_over_request_limit_is_413(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.web.routes.leads.MAX_REQUEST_BYTES", 100)
    client, _, storage, _audit = _client("ceo")
    csrf = _csrf(client)
    response = client.post(
        f"/leads/{LEAD_ID}/comments",
        data={"csrf_token": csrf, "new_comment": "Nota"},
        files=[("files", ("foto.png", _png(), "image/png"))],
        follow_redirects=False,
    )
    assert response.status_code == 413
    assert storage.put_calls == []


def test_text_only_note_still_works_when_attachments_enabled() -> None:
    client, repo, storage, audit = _client("ceo")
    csrf = _csrf(client)
    response = client.post(
        f"/leads/{LEAD_ID}/comments",
        data={"csrf_token": csrf, "new_comment": "Seguimiento simple"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert repo.comments[-1].endswith("Seguimiento simple")
    assert storage.put_calls == []
    assert audit == []


def test_view_requires_session() -> None:
    service = SolicitudService(
        repository=cast(Any, _FakeRepo()),
        settings=Settings(APP_ENV="local", ATTACHMENTS_ENABLED=True, ATTACHMENTS_BUCKET="bucket"),
        storage=cast(Any, _FakeStorage()),
        attachment_audit=lambda **kwargs: None,
    )
    app = create_web_app()
    app.state.web_service = service
    app.state.auth_provider = _AuthProvider("ceo")
    app.state.settings = Settings(
        APP_ENV="local",
        AUTH_ENABLED=True,
        AUTH_MODE="simple-dev",
        ATTACHMENTS_ENABLED=True,
        ATTACHMENTS_BUCKET="bucket",
    )
    response = TestClient(app).get(f"/leads/{LEAD_ID}/adjuntos/{ATTACH_ID}", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers.get("location") == "/login"


def test_view_with_uuid_of_another_lead_is_404_without_s3_call() -> None:
    client, repo, storage, _audit = _client("ceo")
    repo.lead["comentarios"] = "Solicitud original."
    response = client.get(f"/leads/{LEAD_ID}/adjuntos/{ATTACH_ID}")
    assert response.status_code == 404
    assert storage.get_calls == []


def test_view_returns_verified_content_and_security_headers() -> None:
    client, repo, storage, audit = _client("ceo")
    repo.lead["comentarios"] = f"Nota\n[adjunto:png:{ATTACH_ID}]"
    storage.objects[f"leads/{LEAD_ID}/{ATTACH_ID}"] = StoredObject(
        content=_png(),
        content_type="image/png",
        metadata={"verified_type": "png", "size": "0", "sha256": "a" * 64},
    )
    response = client.get(f"/leads/{LEAD_ID}/adjuntos/{ATTACH_ID}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "sandbox" in response.headers["content-security-policy"]
    assert "inline" in response.headers["content-disposition"]
    assert any(event["accion"] == "adjunto_visto" for event in audit)


def test_download_uses_attachment_disposition_and_audits() -> None:
    client, repo, storage, audit = _client("ceo")
    repo.lead["comentarios"] = f"Nota\n[adjunto:pdf:{ATTACH_ID}]"
    storage.objects[f"leads/{LEAD_ID}/{ATTACH_ID}"] = StoredObject(
        content=b"%PDF-1.4\n%%EOF",
        content_type="application/pdf",
        metadata={"verified_type": "pdf", "size": "0", "sha256": "a" * 64},
    )
    response = client.get(f"/leads/{LEAD_ID}/adjuntos/{ATTACH_ID}?descargar=1")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert any(event["accion"] == "adjunto_descargado" for event in audit)


def test_delete_requires_full_pii_role() -> None:
    client, _, storage, audit = _client("executive")
    response = client.post(
        f"/leads/{LEAD_ID}/adjuntos/{ATTACH_ID}/eliminar",
        data={"csrf_token": "x"},
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert storage.delete_calls == []
    assert audit == []


def test_delete_success_leaves_mark_and_audits() -> None:
    client, repo, storage, audit = _client("ceo")
    repo.lead["comentarios"] = f"Nota\n[adjunto:png:{ATTACH_ID}]"
    storage.objects[f"leads/{LEAD_ID}/{ATTACH_ID}"] = StoredObject(
        content=_png(),
        content_type="image/png",
        metadata={"verified_type": "png", "size": "0", "sha256": "a" * 64},
    )
    csrf = _csrf(client)
    response = client.post(
        f"/leads/{LEAD_ID}/adjuntos/{ATTACH_ID}/eliminar",
        data={"csrf_token": csrf, "return_to": "/leads"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert storage.delete_calls == [f"leads/{LEAD_ID}/{ATTACH_ID}"]
    assert "[adjunto:png:" in repo.lead["comentarios"]
    assert any(event["accion"] == "adjunto_eliminado" for event in audit)


def test_detail_page_renders_attachment_controls() -> None:
    client, repo, storage, _audit = _client("ceo")
    repo.lead["comentarios"] = (
        f"Solicitud original.\n\n[23/08/2026 22:32] Ceo Demo\nNota\n[adjunto:png:{ATTACH_ID}]"
    )
    body = client.get(f"/leads/{LEAD_ID}").text
    assert 'alt="Imagen adjunta"' in body
    assert 'loading="lazy"' in body
    assert "adjunto eliminado" in body  # el fallback del onerror
    assert "Eliminar" in body
    # La página no consulta S3 al renderizar.
    assert storage.get_calls == []


def test_view_by_advisor_without_access_is_404_without_s3_call() -> None:
    repo = _FakeRepo()
    repo.owned = False
    repo.lead["comentarios"] = f"Nota\n[adjunto:png:{ATTACH_ID}]"
    client, _, storage, _audit = _client("advisor", repo=repo, advisor_id=ADVISOR_ID)
    response = client.get(f"/leads/{LEAD_ID}/adjuntos/{ATTACH_ID}")
    assert response.status_code == 404
    assert storage.get_calls == []


def test_upload_rate_limited_returns_429_without_s3_call() -> None:
    client, _, storage, _audit = _client("ceo")
    client.app.state.attachment_rate_limiter = InMemoryRateLimiter(
        max_requests=0, window_seconds=600
    )
    csrf = _csrf(client)
    response = client.post(
        f"/leads/{LEAD_ID}/comments",
        data={"csrf_token": csrf, "new_comment": "Nota"},
        files=[("files", ("foto.png", _png(), "image/png"))],
        follow_redirects=False,
    )
    assert response.status_code == 429
    assert storage.put_calls == []


def test_malicious_filename_is_not_stored_or_reflected() -> None:
    client, repo, storage, _audit = _client("ceo")
    csrf = _csrf(client)
    response = client.post(
        f"/leads/{LEAD_ID}/comments",
        data={"csrf_token": csrf, "new_comment": "Nota", "return_to": "/leads"},
        files=[
            (
                "files",
                ("<script>.pdf", b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF", "application/pdf"),
            )
        ],
        follow_redirects=False,
    )
    assert response.status_code == 303
    # El nombre no se guarda en la clave de S3 (uuid del servidor) ni en la nota.
    assert "<script>" not in storage.put_calls[0]
    assert "<script>" not in repo.comments[-1]
    # Ni se refleja en el HTML del detalle.
    detail = client.get(f"/leads/{LEAD_ID}").text
    assert "<script>" not in detail
    assert "../../" not in detail


def test_logs_do_not_contain_bytes_or_filenames(caplog: pytest.LogCaptureFixture) -> None:
    client, _, storage, _audit = _client("ceo")
    csrf = _csrf(client)
    with caplog.at_level(logging.WARNING, logger="app.services.solicitud_service"):
        response = client.post(
            f"/leads/{LEAD_ID}/comments",
            data={"csrf_token": csrf, "new_comment": "Nota", "return_to": "/leads"},
            files=[("files", ("<script>.png", _png(), "image/png"))],
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert "<script>" not in caplog.text
    assert "PNG" not in caplog.text  # los bytes nunca se vuelcan a los logs
    assert storage.put_calls  # la subida sí ocurrió (el log no filtró nada)


def test_disabled_attachments_hide_file_field_and_return_404() -> None:
    client, repo, storage, audit = _client("ceo", attachments_enabled=False)
    # El formulario no muestra el campo de archivos (AC-1).
    body = client.get(f"/leads/{LEAD_ID}").text
    assert 'name="files"' not in body
    assert "Adjuntar archivos" not in body

    # Las rutas de adjuntos responden 404 y no tocan S3.
    response = client.get(f"/leads/{LEAD_ID}/adjuntos/{ATTACH_ID}")
    assert response.status_code == 404
    response = client.post(
        f"/leads/{LEAD_ID}/adjuntos/{ATTACH_ID}/eliminar",
        data={"csrf_token": "x"},
        follow_redirects=False,
    )
    assert response.status_code == 404
    assert storage.get_calls == []
    assert storage.delete_calls == []

    # Una nota de solo texto se agrega exactamente igual (regresión).
    csrf = _csrf(client)
    response = client.post(
        f"/leads/{LEAD_ID}/comments",
        data={"csrf_token": csrf, "new_comment": "Seguimiento simple"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert repo.comments[-1].endswith("Seguimiento simple")
    assert storage.put_calls == []
    assert audit == []
