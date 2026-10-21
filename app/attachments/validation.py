"""Validación por contenido de los adjuntos de las notas (AC-2).

El tipo lo decide el contenido, nunca la extensión ni el ``Content-Type``
declarado por el cliente. Solo se leen las dimensiones de los encabezados de las
imágenes (sin decodificar píxeles). Un resultado válido devuelve el tipo
verificado (``pdf``, ``png`` o ``jpg``), el tamaño y el SHA-256; un rechazo
devuelve un código estable, sin texto del usuario ni contenido.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# Límites fijos de la primera versión (decisión del humano del 2026-10-21).
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MiB por archivo
MAX_FILES_PER_NOTE = 5
MAX_REQUEST_BYTES = 25 * 1024 * 1024  # 25 MiB por petición
MAX_IMAGE_PIXELS = 50_000_000
PDF_EOF_SCAN_BYTES = 1024

# Content-Type servido según el tipo verificado. Nunca el tipo declarado.
ATTACHMENT_MIME_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
}

_EMPTY_FILE = "empty_file"
_TOO_LARGE = "too_large"
_UNSUPPORTED_TYPE = "unsupported_type"
_INVALID_CONTENT = "invalid_content"
_UNSAFE_PDF = "unsafe_pdf"
_TOO_MANY_PIXELS = "too_many_pixels"

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_IEND = b"IEND"
_JPEG_SOI = b"\xff\xd8"

# Marcadores SOF válidos (start of frame); excluye DHT (0xC4), JPG (0xC8) y DAC
# (0xCC) que no llevan dimensiones.
_JPEG_SOF_MARKERS = frozenset(
    {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
)

# Nombres de PDF prohibidos por llevar partes activas o cifrado.
_FORBIDDEN_PDF_TOKENS = ("/JS", "/JavaScript", "/Launch", "/EmbeddedFile", "/Encrypt")


class AttachmentValidationError(ValueError):
    """Rechazo de un adjunto con un código estable (sin texto del usuario)."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ValidatedAttachment:
    """Adjunto verificado por contenido, listo para almacenar."""

    attachment_type: str  # "pdf" | "png" | "jpg"
    size: int
    sha256: str
    content: bytes


def validate_attachment_content(content: bytes) -> ValidatedAttachment:
    """Valida el contenido y devuelve el adjunto verificado, o rechaza.

    Orden de los rechazos (AC-2): archivo vacío, más de 10 MiB, tipo no
    permitido, firma válida con estructura inválida/truncada, imagen con
    dimensiones sobre el tope y PDF con partes activas.
    """
    if not content:
        raise AttachmentValidationError(_EMPTY_FILE)
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise AttachmentValidationError(_TOO_LARGE)

    attachment_type = _detect_type(content)
    if attachment_type is None:
        raise AttachmentValidationError(_UNSUPPORTED_TYPE)

    if attachment_type == "pdf":
        _validate_pdf(content)
    elif attachment_type == "png":
        width, height = _png_dimensions(content)
        _enforce_pixel_limit(width, height)
    else:  # jpg
        dimensions = _jpeg_dimensions(content)
        if dimensions is None:
            raise AttachmentValidationError(_INVALID_CONTENT)
        width, height = dimensions
        _enforce_pixel_limit(width, height)

    return ValidatedAttachment(
        attachment_type=attachment_type,
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        content=content,
    )


def _detect_type(content: bytes) -> str | None:
    if content.startswith(_PNG_SIGNATURE):
        return "png"
    if content.startswith(_JPEG_SOI):
        return "jpg"
    if content.startswith(b"%PDF-"):
        return "pdf"
    return None


def _enforce_pixel_limit(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise AttachmentValidationError(_INVALID_CONTENT)
    if width * height > MAX_IMAGE_PIXELS:
        raise AttachmentValidationError(_TOO_MANY_PIXELS)


def _png_dimensions(content: bytes) -> tuple[int, int]:
    """Lee ancho y alto del IHDR sin decodificar píxeles.

    Rechaza un PNG con firma válida pero truncado o sin el bloque IHDR completo,
    y un archivo que no termina con IEND (truncado a mitad de camino).
    """
    # firma (8) + longitud IHDR (4) + "IHDR" (4) + datos IHDR (13) + CRC (4)
    if len(content) < 33:
        raise AttachmentValidationError(_INVALID_CONTENT)
    if content[12:16] != b"IHDR":
        raise AttachmentValidationError(_INVALID_CONTENT)
    ihdr_length = int.from_bytes(content[8:12], "big")
    if ihdr_length != 13:
        raise AttachmentValidationError(_INVALID_CONTENT)
    width = int.from_bytes(content[16:20], "big")
    height = int.from_bytes(content[20:24], "big")
    if content[-8:-4] != _PNG_IEND:
        raise AttachmentValidationError(_INVALID_CONTENT)
    return width, height


def _jpeg_dimensions(content: bytes) -> tuple[int, int] | None:
    """Lee ancho y alto del primer marcador SOF sin decodificar píxeles."""
    if len(content) < 4 or not content.startswith(_JPEG_SOI):
        return None

    index = 2
    while index < len(content):
        # Saltar bytes de relleno hasta el marcador.
        while index < len(content) and content[index] != 0xFF:
            index += 1
        while index < len(content) and content[index] == 0xFF:
            index += 1
        if index >= len(content):
            return None

        marker = content[index]
        index += 1

        if marker == 0xD8:  # SOI (solo debería aparecer al inicio)
            continue
        if marker in (0xD9, 0xDA):  # EOI o SOS: no hay SOF -> inválido
            return None
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            # Marcadores sin longitud.
            continue

        if index + 2 > len(content):
            return None
        segment_length = int.from_bytes(content[index : index + 2], "big")
        if segment_length < 2:
            return None

        if marker in _JPEG_SOF_MARKERS:
            if index + 7 > len(content):
                return None
            height = int.from_bytes(content[index + 3 : index + 5], "big")
            width = int.from_bytes(content[index + 5 : index + 7], "big")
            return width, height

        index += segment_length

    return None


def _validate_pdf(content: bytes) -> None:
    """Rechaza PDF truncado o con partes activas / cifrado (AC-2)."""
    if b"%%EOF" not in content[-PDF_EOF_SCAN_BYTES:]:
        raise AttachmentValidationError(_INVALID_CONTENT)

    decoded = _decode_pdf_name_escapes(content)
    for token in _FORBIDDEN_PDF_TOKENS:
        if token in decoded:
            raise AttachmentValidationError(_UNSAFE_PDF)


def _decode_pdf_name_escapes(content: bytes) -> str:
    """Decodifica los escapes ``#xx`` de los nombres de PDF antes de comparar.

    Un nombre como ``/J#53`` representa ``/JS`` (0x53 = 'S'); se decodifica a
    ``latin-1`` para conservar el byte exacto y detectar los tokens prohibidos.
    """
    output = bytearray()
    index = 0
    while index < len(content):
        byte = content[index]
        if (
            byte == 0x23  # '#'
            and index + 2 < len(content)
            and _is_hex(content[index + 1])
            and _is_hex(content[index + 2])
        ):
            output.append(int(content[index + 1 : index + 3], 16))
            index += 3
            continue
        output.append(byte)
        index += 1
    return output.decode("latin-1")


def _is_hex(byte: int) -> bool:
    return 0x30 <= byte <= 0x39 or 0x41 <= byte <= 0x46 or 0x61 <= byte <= 0x66
