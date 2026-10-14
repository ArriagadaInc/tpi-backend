"""Escritor del evento funcional de auditoría del simulador de renta vitalicia (SIM-RV-V1).

Este módulo existe dentro de ``app/services/**`` (no en ``app/repositories/**``) por una
decisión explícita de alcance de la tarea ``SIM-RV-V1`` (ver ``docs/SIM_RV_V1_PENDIENTES.md``
§2 y ``docs/BITACORA.md``): el guard del Harness no permite editar ``app/repositories/**`` en
esta tarea y el alcance no es ampliable. Por eso el escritor abre su propia conexión con
``get_db_connection`` de ``app.database.connection``, repitiendo el patrón de INSERT append-only
que ya usa ``SolicitudRepository.record_xlsx_export_event``.

Esto se aparta de la convención de capas vigente (los servicios no abren conexiones hoy). La
deuda está documentada y el traslado a ``app/repositories/`` queda para una tarea posterior con
ese alcance.

El evento es append-only y no lleva PII: ``detalle`` contiene únicamente ``actor_subject``,
``role``, ``tipo_escenario``, ``version_modelo`` y ``codigo_verificacion``. Nunca saldo, tasa,
resultados, nombres ni datos personales (AC-11).
"""

from __future__ import annotations

import json
from typing import Any

from app.database.connection import get_db_connection

ACCION_SIMULACION = "simulacion_renta_vitalicia"
TABLA_AFECTADA = "tpi.leads"


def record_simulacion_event(
    *,
    id_lead: Any,
    actor_subject: str,
    role: str,
    tipo_escenario: str,
    version_modelo: str,
    codigo_verificacion: str,
) -> None:
    """Inserta un evento append-only en ``tpi.auditoria`` para un PDF generado con éxito.

    ``detalle`` es JSON con metadatos funcionales sin PII. ``id_usuario``/``id_persona``
    quedan ``NULL`` (no hay una identidad de usuario persistida para el backoffice web);
    ``id_lead`` identifica al lead simulado. La aplicación nunca lee ``tpi.auditoria``
    directamente; es el mismo camino de escritura ya concedido a ``tpi_app`` por la
    migración 006 (sin cambio de esquema, clase A).
    """
    query = """
        INSERT INTO tpi.auditoria
            (id_usuario, id_persona, id_lead, accion, tabla_afectada, detalle)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    detalle = {
        "actor_subject": actor_subject,
        "role": role,
        "tipo_escenario": tipo_escenario,
        "version_modelo": version_modelo,
        "codigo_verificacion": codigo_verificacion,
    }
    with get_db_connection(operation="record_simulacion_event") as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        None,
                        None,
                        id_lead,
                        ACCION_SIMULACION,
                        TABLA_AFECTADA,
                        json.dumps(detalle),
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
