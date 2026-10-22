"""Almacenamiento privado en S3 detrás de una interfaz inyectable (AC-3).

Sigue el patrón de ``app/notifications/sns.py``: un ``Protocol`` pequeño que un
doble de pruebas implementa sin red. Un ``403`` o ``NoSuchKey`` de S3 se tratan
igual: adjunto no disponible (el bucket no entrega lo que aún no se escaneó, lo
infectado ni lo borrado, y no se puede listar).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings


class AttachmentStorage(Protocol):
    """Interfaz de almacenamiento de adjuntos, fácil de simular en pruebas."""

    def put(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str,
        metadata: dict[str, str],
    ) -> None: ...

    def get(self, key: str) -> StoredObject | None: ...

    def get_tagging(self, key: str) -> dict[str, str] | None: ...

    def delete(self, key: str) -> None: ...


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Objeto leído de S3 con sus metadatos verificados."""

    content: bytes
    content_type: str
    metadata: dict[str, str]


class S3Client(Protocol):
    """Superficie mínima de boto3 usada por el adaptador."""

    def put_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_object_tagging(self, **kwargs: Any) -> dict[str, Any]: ...

    def delete_object(self, **kwargs: Any) -> dict[str, Any]: ...


class S3AttachmentStorage:
    """Cliente S3 real, sin etiquetas ni listado (la política lo deniega)."""

    provider = "s3"

    def __init__(
        self, bucket: str, client: S3Client | None = None, region_name: str = "us-east-2"
    ) -> None:
        self.bucket = bucket
        self.client = client or boto3.client("s3", region_name=region_name)

    def put(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str,
        metadata: dict[str, str],
    ) -> None:
        # Nunca Tagging ni PutObjectTagging: la política del bucket las deniega y
        # las etiquetas las pone solo GuardDuty.
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            Metadata=metadata,
        )

    def get(self, key: str) -> StoredObject | None:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except (ClientError, BotoCoreError):
            # NoSuchKey, 403 (aún sin escanear/infectado) y un fallo de red de
            # botocore se tratan igual: adjunto no disponible (404 genérico).
            return None
        body = response.get("Body")
        if body is None:
            return None
        content = body.read()
        return StoredObject(
            content=content,
            content_type=str(response.get("ContentType") or ""),
            metadata=_stringify_metadata(response.get("Metadata")),
        )

    def get_tagging(self, key: str) -> dict[str, str] | None:
        """Lee las etiquetas del objeto (solo lectura, AC-5).

        Un ``ClientError`` (incluido ``AccessDenied`` por falta del permiso) o un
        fallo de red devuelven ``None``: la página lo muestra como «No
        disponible». El adaptador nunca llama a ``PutObjectTagging`` ni a
        ``DeleteObjectTagging`` (las etiquetas solo las escribe GuardDuty).
        """
        try:
            response = self.client.get_object_tagging(Bucket=self.bucket, Key=key)
        except (ClientError, BotoCoreError):
            return None
        tag_set = response.get("TagSet") or []
        return {
            str(tag.get("Key")): str(tag.get("Value"))
            for tag in tag_set
            if isinstance(tag, dict) and tag.get("Key") is not None
        }

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


class DisabledAttachmentStorage:
    """Valor seguro cuando la función está apagada: nunca hay adjuntos."""

    provider = "none"

    def put(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str,
        metadata: dict[str, str],
    ) -> None:
        del key, body, content_type, metadata
        raise RuntimeError("Adjuntos deshabilitados")

    def get(self, key: str) -> StoredObject | None:
        del key
        return None

    def get_tagging(self, key: str) -> dict[str, str] | None:
        del key
        return None

    def delete(self, key: str) -> None:
        del key


def build_attachment_storage(settings: Settings) -> AttachmentStorage:
    """Compone el almacenamiento según la configuración fail-closed."""
    if not settings.attachments_enabled:
        return DisabledAttachmentStorage()
    if not settings.attachments_bucket:
        # La validación de Settings impide arrancar en este estado, pero el
        # adaptador falla cerrado si alguien lo construye igual.
        return DisabledAttachmentStorage()
    return S3AttachmentStorage(
        settings.attachments_bucket,
        region_name=settings.attachments_s3_region,
    )


def _stringify_metadata(metadata: Any) -> dict[str, str]:
    if not isinstance(metadata, dict):
        return {}
    return {str(key): str(value) for key, value in metadata.items()}
