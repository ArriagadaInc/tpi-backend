"""Adjuntos de notas (CRM-ADJUNTOS-2-CODIGO).

Validación por contenido, marcas en ``tpi.leads.comentarios``, almacenamiento
privado en S3 detrás de una interfaz inyectable y auditoría append-only.
"""

from app.attachments.marks import (
    AttachmentMark,
    build_attachment_mark,
    match_full_attachment_mark,
    parse_attachment_marks,
    strip_attachment_marks,
)
from app.attachments.storage import (
    AttachmentStorage,
    DisabledAttachmentStorage,
    S3AttachmentStorage,
    StoredObject,
    build_attachment_storage,
)
from app.attachments.validation import (
    ATTACHMENT_MIME_TYPES,
    MAX_ATTACHMENT_BYTES,
    MAX_FILES_PER_NOTE,
    MAX_IMAGE_PIXELS,
    MAX_REQUEST_BYTES,
    AttachmentValidationError,
    ValidatedAttachment,
    validate_attachment_content,
)

__all__ = [
    "ATTACHMENT_MIME_TYPES",
    "MAX_ATTACHMENT_BYTES",
    "MAX_FILES_PER_NOTE",
    "MAX_IMAGE_PIXELS",
    "MAX_REQUEST_BYTES",
    "AttachmentMark",
    "AttachmentStorage",
    "AttachmentValidationError",
    "DisabledAttachmentStorage",
    "S3AttachmentStorage",
    "StoredObject",
    "ValidatedAttachment",
    "build_attachment_mark",
    "build_attachment_storage",
    "match_full_attachment_mark",
    "parse_attachment_marks",
    "strip_attachment_marks",
    "validate_attachment_content",
]
