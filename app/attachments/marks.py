"""Marcas de adjuntos en ``tpi.leads.comentarios`` (sin tabla nueva).

La relación nota-adjunto es una marca ``[adjunto:<tipo>:<uuid>]`` agregada por el
servidor al final de la nota, con ``<tipo>`` = ``pdf``, ``png`` o ``jpg``. El
intérprete es estricto: lo que no calza es texto normal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

_ATTACHMENT_TYPES = ("pdf", "png", "jpg")

# UUID canónico: 8-4-4-4-12 en hexadecimal.
_UUID_PATTERN = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

_ATTACHMENT_MARK_RE = re.compile(rf"\[adjunto:(pdf|png|jpg):({_UUID_PATTERN})\]")
_ATTACHMENT_MARK_FULL_RE = re.compile(rf"\[adjunto:(pdf|png|jpg):({_UUID_PATTERN})\]\Z")

# Prefijo de una marca imitada por el usuario. Se neutraliza en el momento de
# escribir la nota para que jamás se confunda con una marca del servidor.
_MARK_PREFIX_RE = re.compile(r"\[adjunto:", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class AttachmentMark:
    """Una marca de adjunto interpretada desde el texto de una nota."""

    attachment_type: str  # "pdf" | "png" | "jpg"
    attachment_id: UUID


def build_attachment_mark(attachment_type: str, attachment_id: UUID) -> str:
    """Construye la marca canónica que el servidor agrega a la nota."""
    if attachment_type not in _ATTACHMENT_TYPES:
        raise ValueError(f"Tipo de adjunto no permitido: {attachment_type}")
    return f"[adjunto:{attachment_type}:{attachment_id}]"


def parse_attachment_marks(text: str | None) -> list[AttachmentMark]:
    """Devuelve, en orden, las marcas válidas presentes en ``text``."""
    if not text:
        return []
    return [
        AttachmentMark(attachment_type=match.group(1), attachment_id=UUID(match.group(2)))
        for match in _ATTACHMENT_MARK_RE.finditer(text)
    ]


def match_full_attachment_mark(line: str) -> AttachmentMark | None:
    """Devuelve la marca si ``line`` completa es exactamente una marca válida."""
    match = _ATTACHMENT_MARK_FULL_RE.match(line.strip())
    if match is None:
        return None
    return AttachmentMark(attachment_type=match.group(1), attachment_id=UUID(match.group(2)))


def strip_attachment_marks(text: str | None) -> str:
    """Quita todas las marcas válidas del texto (vista, resúmenes y exportación)."""
    if not text:
        return text or ""
    return _ATTACHMENT_MARK_RE.sub("", text)


def neutralize_attachment_marks(text: str) -> str:
    """Neutraliza una marca escrita a mano para que nunca sea una marca real.

    Se aplica al texto del usuario antes de guardarlo: el ``:`` se escribe como
    la entidad HTML ``&#58;``, que se muestra igual en el navegador pero no
    coincide con la expresión regular de las marcas. Así un usuario que escribe
    ``[adjunto:...]`` no puede fabricar un adjunto.
    """
    return _MARK_PREFIX_RE.sub("[adjunto&#58;", text)
