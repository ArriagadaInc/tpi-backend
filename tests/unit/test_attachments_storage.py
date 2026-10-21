"""Pruebas del adaptador S3 de adjuntos con un doble sin red (AC-3)."""

from __future__ import annotations

from typing import Any

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from app.attachments.storage import (
    DisabledAttachmentStorage,
    S3AttachmentStorage,
    build_attachment_storage,
)
from app.config import Settings


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}
        self.tags: dict[str, dict[str, str]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("put_object", kwargs))
        self.objects[str(kwargs["Key"])] = kwargs
        return {}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_object", kwargs))
        if str(kwargs["Key"]) not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")
        stored = self.objects[str(kwargs["Key"])]
        body = type("Body", (), {"read": lambda self: stored["Body"]})()
        return {"Body": body, "ContentType": stored["ContentType"], "Metadata": stored["Metadata"]}

    def get_object_tagging(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_object_tagging", kwargs))
        key = str(kwargs["Key"])
        if key not in self.tags:
            raise ClientError(
                {"Error": {"Code": "NoSuchTagSet", "Message": "missing"}},
                "GetObjectTagging",
            )
        return {
            "TagSet": [
                {"Key": tag_key, "Value": tag_value}
                for tag_key, tag_value in self.tags[key].items()
            ]
        }

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("delete_object", kwargs))
        self.objects.pop(str(kwargs["Key"]), None)
        return {}


def test_put_never_tags_and_stores_verified_metadata() -> None:
    client = _FakeS3Client()
    storage = S3AttachmentStorage(bucket="b", client=client)
    storage.put(
        "leads/1/2",
        b"x",
        content_type="application/pdf",
        metadata={"verified_type": "pdf", "size": "1", "sha256": "abc"},
    )
    kwargs = client.calls[0][1]
    assert kwargs["Bucket"] == "b"
    assert kwargs["Key"] == "leads/1/2"
    assert kwargs["ContentType"] == "application/pdf"
    assert kwargs["Metadata"] == {"verified_type": "pdf", "size": "1", "sha256": "abc"}
    assert "Tagging" not in kwargs


def test_get_returns_content_and_metadata() -> None:
    client = _FakeS3Client()
    storage = S3AttachmentStorage(bucket="b", client=client)
    storage.put("leads/1/2", b"hola", content_type="image/png", metadata={"verified_type": "png"})
    stored = storage.get("leads/1/2")
    assert stored is not None
    assert stored.content == b"hola"
    assert stored.metadata["verified_type"] == "png"


def test_get_returns_none_on_client_error() -> None:
    client = _FakeS3Client()
    storage = S3AttachmentStorage(bucket="b", client=client)
    assert storage.get("leads/1/missing") is None


def test_get_returns_none_on_access_denied_403() -> None:
    # Un 403 (aún sin escanear o infectado) se trata igual que NoSuchKey:
    # adjunto no disponible, sin distinguir la causa (AC-3).
    class _DeniedClient:
        def put_object(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            return {}

        def get_object(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "denied"}},
                "GetObject",
            )

        def delete_object(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            return {}

    storage = S3AttachmentStorage(bucket="b", client=_DeniedClient())
    assert storage.get("leads/1/2") is None


def test_get_returns_none_on_network_error() -> None:
    # Un fallo de red de botocore (no ClientError) también es «adjunto no
    # disponible» y no debe propagarse como 500 (F-4).
    class _NetworkClient:
        def put_object(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            return {}

        def get_object(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            raise BotoCoreError

        def delete_object(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            return {}

    storage = S3AttachmentStorage(bucket="b", client=_NetworkClient())
    assert storage.get("leads/1/2") is None


def test_delete_calls_delete_object() -> None:
    client = _FakeS3Client()
    storage = S3AttachmentStorage(bucket="b", client=client)
    storage.delete("leads/1/2")
    assert client.calls[0][0] == "delete_object"


def test_get_tagging_reads_tags_and_never_writes() -> None:
    client = _FakeS3Client()
    client.tags["leads/1/2"] = {"GuardDutyMalwareScanStatus": "NO_THREATS_FOUND"}
    storage = S3AttachmentStorage(bucket="b", client=client)
    assert storage.get_tagging("leads/1/2") == {"GuardDutyMalwareScanStatus": "NO_THREATS_FOUND"}
    called = [call[0] for call in client.calls]
    assert called == ["get_object_tagging"]
    assert "put_object_tagging" not in called
    assert "delete_object_tagging" not in called


def test_get_tagging_returns_none_on_access_denied() -> None:
    class _DeniedTaggingClient:
        def put_object(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            return {}

        def get_object(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            return {}

        def get_object_tagging(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "denied"}},
                "GetObjectTagging",
            )

        def delete_object(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            return {}

    storage = S3AttachmentStorage(bucket="b", client=_DeniedTaggingClient())
    assert storage.get_tagging("leads/1/2") is None


def test_get_tagging_returns_none_on_network_error() -> None:
    class _NetworkTaggingClient:
        def put_object(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            return {}

        def get_object(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            return {}

        def get_object_tagging(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            raise BotoCoreError

        def delete_object(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            return {}

    storage = S3AttachmentStorage(bucket="b", client=_NetworkTaggingClient())
    assert storage.get_tagging("leads/1/2") is None


def test_disabled_storage_get_returns_none_and_put_raises() -> None:
    storage = DisabledAttachmentStorage()
    assert storage.get("x") is None
    try:
        storage.put("x", b"", content_type="application/pdf", metadata={})
    except RuntimeError:
        pass
    else:
        raise AssertionError("put should raise when disabled")


def test_build_attachment_storage_fails_closed_when_disabled() -> None:
    assert isinstance(
        build_attachment_storage(Settings(APP_ENV="testing", ATTACHMENTS_ENABLED=False)),
        DisabledAttachmentStorage,
    )


def test_settings_rejects_enabled_without_bucket() -> None:
    # AC-1: con ATTACHMENTS_ENABLED=true y sin bucket la app no arranca (fail-closed).
    with pytest.raises(ValueError):
        Settings(APP_ENV="testing", ATTACHMENTS_ENABLED=True, ATTACHMENTS_BUCKET=None)


def test_settings_accepts_enabled_with_bucket() -> None:
    settings = Settings(
        APP_ENV="testing",
        ATTACHMENTS_ENABLED=True,
        ATTACHMENTS_BUCKET="bucket",
    )
    assert settings.attachments_enabled is True
    assert settings.attachments_bucket == "bucket"


def test_settings_allow_pdf_embedded_files_defaults_true() -> None:
    # Decisión 9: se permiten por defecto; el ajuste permite volver al rechazo.
    assert Settings(APP_ENV="testing").attachments_allow_pdf_embedded_files is True
    assert (
        Settings(
            APP_ENV="testing",
            ATTACHMENTS_ALLOW_PDF_EMBEDDED_FILES=False,
        ).attachments_allow_pdf_embedded_files
        is False
    )
