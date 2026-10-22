"""Escritor de eventos de auditoría de adjuntos (AC-7).

Sigue el patrón de ``app/services/simulador_auditoria.py``: el evento es
append-only en ``tpi.auditoria`` (``tabla_afectada`` = ``tpi.leads``) y el
``detalle`` es JSON con el sujeto, el ``uuid``, el tipo, el tamaño y el SHA-256;
para los rechazos solo el código de rechazo. Nunca nombres de archivo ni
contenido.
"""

from __future__ import annotations

import json
from typing import Any

from app.database.connection import get_db_connection

ACCION_SUBIDO = "adjunto_subido"
ACCION_RECHAZADO = "adjunto_rechazado"
ACCION_VISTO = "adjunto_visto"
ACCION_DESCARGADO = "adjunto_descargado"
ACCION_ELIMINADO = "adjunto_eliminado"
TABLA_AFECTADA = "tpi.leads"

DETALLE_SCHEMA_VERSION = 1


def _detalle(
    *,
    actor_subject: str,
    attachment_id: str,
    attachment_type: str | None,
    size: int | None,
    sha256: str | None,
    rejection_code: str | None = None,
    archivos_incrustados: bool | None = None,
) -> dict[str, Any]:
    """Construye el ``detalle`` versionado sin nombres de archivo ni contenido."""
    return {
        "schema_version": DETALLE_SCHEMA_VERSION,
        "actor_subject": actor_subject,
        "adjunto_uuid": attachment_id,
        "tipo": attachment_type,
        "tamano": size,
        "sha256": sha256,
        "codigo_rechazo": rejection_code,
        "archivos_incrustados": archivos_incrustados,
    }


def record_attachment_event(
    *,
    accion: str,
    id_lead: Any,
    actor_subject: str,
    attachment_id: str,
    attachment_type: str | None = None,
    size: int | None = None,
    sha256: str | None = None,
    rejection_code: str | None = None,
    archivos_incrustados: bool | None = None,
) -> None:
    """Inserta un evento append-only en ``tpi.auditoria`` para una acción de adjunto."""
    query = """
        INSERT INTO tpi.auditoria
            (id_usuario, id_persona, id_lead, accion, tabla_afectada, detalle)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    detalle = _detalle(
        actor_subject=actor_subject,
        attachment_id=attachment_id,
        attachment_type=attachment_type,
        size=size,
        sha256=sha256,
        rejection_code=rejection_code,
        archivos_incrustados=archivos_incrustados,
    )
    with get_db_connection(operation="record_attachment_event") as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        None,
                        None,
                        id_lead,
                        accion,
                        TABLA_AFECTADA,
                        json.dumps(detalle),
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
