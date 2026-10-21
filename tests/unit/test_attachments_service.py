"""Pruebas de orquestación de adjuntos en SolicitudService (AC-4, AC-6, AC-7)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.attachments.storage import StoredObject
from app.attachments.validation import ValidatedAttachment
from app.auth.models import AuthenticatedUser
from app.config import Settings
from app.services.solicitud_service import SolicitudService

LEAD_ID = UUID("11111111-1111-1111-1111-111111111111")
ADVISOR_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ATTACH_ID = UUID("22222222-2222-2222-2222-222222222222")

PDF_CONTENT = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"


def _pdf_attachment() -> ValidatedAttachment:
    return ValidatedAttachment(
        attachment_type="pdf",
        size=len(PDF_CONTENT),
        sha256="a" * 64,
        content=PDF_CONTENT,
    )


def _user(role: str = "ceo", *, advisor_id: UUID | None = None) -> AuthenticatedUser:
    return AuthenticatedUser(
        subject=f"subject-{role}",
        username=f"{role}.local",
        display_name=f"{role.title()} Demo",
        role=role,  # type: ignore[arg-type]
        advisor_id=advisor_id,
    )


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
        }
        self.comments: list[tuple[UUID, str, UUID | None]] = []
        self.owned = True
        self.advisor_active = True
        self.append_result = True
        self.audit_events: list[dict[str, Any]] = []

    def get_solicitud_by_id(self, id_lead: UUID) -> dict[str, Any] | None:
        return dict(self.lead) if str(id_lead) == str(LEAD_ID) else None

    def append_lead_comment(
        self, id_lead: UUID, fragment: str, *, advisor_scope: UUID | None = None
    ) -> bool:
        self.comments.append((id_lead, fragment, advisor_scope))
        return self.append_result

    def lead_active_assignment_belongs_to(self, id_lead: UUID, id_asesor: UUID) -> bool:
        return self.owned

    def get_active_advisor_by_id(self, id_asesor: UUID) -> dict[str, Any] | None:
        if self.advisor_active:
            return {
                "id_asesor": str(id_asesor),
                "rol": "asesor",
                "estado_disponibilidad": "activo",
            }
        return None

    def test_lead_exists(self, id_lead: UUID) -> bool:
        return str(id_lead) == str(LEAD_ID)

    def delete_test_lead(self, id_lead: UUID) -> bool:
        return True


def _service(
    repo: _FakeRepo | None = None,
    storage: _FakeStorage | None = None,
    *,
    attachments_enabled: bool = True,
) -> tuple[SolicitudService, _FakeRepo, _FakeStorage, list[dict[str, Any]]]:
    repo = repo or _FakeRepo()
    storage = storage or _FakeStorage()
    audit_events: list[dict[str, Any]] = []

    def audit(**kwargs: Any) -> None:
        audit_events.append(dict(kwargs))

    settings = Settings(
        APP_ENV="local",
        AUTH_ENABLED=True,
        AUTH_MODE="simple-dev",
        ATTACHMENTS_ENABLED=attachments_enabled,
        ATTACHMENTS_BUCKET="bucket",
    )
    service = SolicitudService(
        repository=repo,  # type: ignore[arg-type]
        settings=settings,
        storage=storage,  # type: ignore[arg-type]
        attachment_audit=audit,
    )
    return service, repo, storage, audit_events


def test_append_with_attachments_uploads_appends_and_audits() -> None:
    service, repo, storage, audit = _service()
    updated = service.append_lead_comment_with_attachments(
        LEAD_ID,
        "Nota con archivo",
        [_pdf_attachment()],
        actor=_user("ceo"),
    )
    assert updated is True
    assert len(storage.put_calls) == 1
    assert storage.put_calls[0].startswith(f"leads/{LEAD_ID}/")
    assert len(repo.comments) == 1
    fragment = repo.comments[0][1]
    assert "Nota con archivo" in fragment
    assert "[adjunto:pdf:" in fragment
    assert len(audit) == 1
    assert audit[0]["accion"] == "adjunto_subido"
    assert audit[0]["attachment_type"] == "pdf"


def test_append_with_attachments_advisor_non_owned_makes_no_s3_call() -> None:
    repo = _FakeRepo()
    repo.owned = False
    service, _, storage, audit = _service(repo)
    updated = service.append_lead_comment_with_attachments(
        LEAD_ID,
        "Nota",
        [_pdf_attachment()],
        actor=_user("advisor", advisor_id=ADVISOR_ID),
    )
    assert updated is False
    assert storage.put_calls == []
    assert storage.delete_calls == []
    assert audit == []


def test_append_failure_deletes_uploaded_objects() -> None:
    repo = _FakeRepo()
    repo.append_result = False
    service, _, storage, _audit = _service(repo)
    updated = service.append_lead_comment_with_attachments(
        LEAD_ID,
        "Nota",
        [_pdf_attachment()],
        actor=_user("ceo"),
    )
    assert updated is False
    assert len(storage.put_calls) == 1
    assert storage.delete_calls == storage.put_calls


def test_can_append_comment_to_lead_honors_advisor_scope() -> None:
    repo = _FakeRepo()
    service, _, _, _ = _service(repo)
    assert service.can_append_comment_to_lead(LEAD_ID, _user("ceo")) is True
    repo.owned = True
    assert (
        service.can_append_comment_to_lead(LEAD_ID, _user("advisor", advisor_id=ADVISOR_ID)) is True
    )
    repo.owned = False
    assert (
        service.can_append_comment_to_lead(LEAD_ID, _user("advisor", advisor_id=ADVISOR_ID))
        is False
    )


def test_get_attachment_returns_content_and_audits_view() -> None:
    service, repo, storage, audit = _service()
    # Prepara el lead con la marca del adjunto.
    repo.lead["comentarios"] = (
        f"Solicitud.\n\n[23/08/2026 22:32] Ceo Demo\nNota\n[adjunto:pdf:{ATTACH_ID}]"
    )
    key = f"leads/{LEAD_ID}/{ATTACH_ID}"
    storage.objects[key] = StoredObject(
        content=PDF_CONTENT,
        content_type="application/pdf",
        metadata={"verified_type": "pdf", "size": str(len(PDF_CONTENT)), "sha256": "a" * 64},
    )

    stored = service.get_attachment(LEAD_ID, ATTACH_ID, actor=_user("ceo"), as_download=False)
    assert stored is not None
    assert stored.content == PDF_CONTENT
    assert audit[0]["accion"] == "adjunto_visto"


def test_get_attachment_with_uuid_of_another_lead_is_none_without_s3_call() -> None:
    service, repo, storage, audit = _service()
    repo.lead["comentarios"] = "Solicitud original."
    stored = service.get_attachment(LEAD_ID, ATTACH_ID, actor=_user("ceo"), as_download=False)
    assert stored is None
    assert storage.get_calls == []
    assert audit == []


def test_get_attachment_with_metadata_type_mismatch_is_none() -> None:
    service, repo, storage, _audit = _service()
    repo.lead["comentarios"] = f"Nota\n[adjunto:png:{ATTACH_ID}]"
    storage.objects[f"leads/{LEAD_ID}/{ATTACH_ID}"] = StoredObject(
        content=b"x", content_type="application/pdf", metadata={"verified_type": "pdf"}
    )
    assert service.get_attachment(LEAD_ID, ATTACH_ID, actor=_user("ceo"), as_download=False) is None


def test_get_attachment_with_s3_403_is_none() -> None:
    service, repo, storage, _audit = _service()
    repo.lead["comentarios"] = f"Nota\n[adjunto:pdf:{ATTACH_ID}]"
    assert service.get_attachment(LEAD_ID, ATTACH_ID, actor=_user("ceo"), as_download=False) is None


def test_delete_attachment_deletes_and_audits() -> None:
    service, repo, storage, audit = _service()
    repo.lead["comentarios"] = f"Nota\n[adjunto:pdf:{ATTACH_ID}]"
    key = f"leads/{LEAD_ID}/{ATTACH_ID}"
    storage.objects[key] = StoredObject(
        content=PDF_CONTENT,
        content_type="application/pdf",
        metadata={"verified_type": "pdf", "size": str(len(PDF_CONTENT)), "sha256": "a" * 64},
    )
    assert service.delete_attachment(LEAD_ID, ATTACH_ID, actor=_user("ceo")) is True
    assert storage.delete_calls == [key]
    assert audit[0]["accion"] == "adjunto_eliminado"
    # La marca queda en la nota.
    assert "[adjunto:pdf:" in repo.lead["comentarios"]


def test_delete_attachment_requires_full_pii_role() -> None:
    service, repo, storage, audit = _service()
    repo.lead["comentarios"] = f"Nota\n[adjunto:pdf:{ATTACH_ID}]"
    assert service.delete_attachment(LEAD_ID, ATTACH_ID, actor=_user("executive")) is False
    assert storage.delete_calls == []
    assert audit == []


def test_audit_attachment_rejection_audits_code_only() -> None:
    service, _, _, audit = _service()
    service.audit_attachment_rejection(LEAD_ID, actor=_user("ceo"), rejection_code="unsafe_pdf")
    assert audit[0]["accion"] == "adjunto_rechazado"
    assert audit[0]["rejection_code"] == "unsafe_pdf"
