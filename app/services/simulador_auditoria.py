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

El evento es append-only. ``detalle`` es JSON versionado (``schema_version``) con los metadatos
funcionales, las entradas y el resultado de la simulación (SIM-EVIDENCIA-ENTRADAS). No lleva PII
directa: sin nombres, RUT, correo ni teléfono, y sin el contenido del PDF. Las fechas de
nacimiento y la composición familiar son datos personales mínimos que se guardan únicamente aquí
(escritura: la aplicación no lee ``tpi.auditoria`` para este flujo).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.database.connection import get_db_connection
from app.simulador_pension.modelos import Hijo, Persona, Resultado

ACCION_SIMULACION = "simulacion_renta_vitalicia"
TABLA_AFECTADA = "tpi.leads"

# Versión del esquema del ``detalle``. Al cambiar su forma, incrementar y no reinterpretar
# versiones anteriores como si fueran la actual (el detalle es de solo escritura por hoy).
DETALLE_SCHEMA_VERSION = 1


def _beneficiarios(
    *,
    conyuge: Persona | None,
    hijos: tuple[Hijo, ...],
) -> list[dict[str, Any]]:
    """Beneficiarios (cónyuge e hijos) con claves estables y sin nombres ni identificadores.

    El cónyuge no tiene condición de invalidez ni «común» en el modelo; esos campos van ``null``.
    Los hijos se ordenan por (fecha de nacimiento, sexo) para un detalle determinístico.
    """
    beneficiarios: list[dict[str, Any]] = []
    if conyuge is not None:
        beneficiarios.append(
            {
                "parentesco": "conyuge",
                "sexo": conyuge.sexo,
                "fecha_nacimiento": conyuge.nacimiento.isoformat(),
                "invalidez": None,
                "comun": None,
            }
        )
    for hijo in sorted(hijos, key=lambda h: (h.nacimiento.isoformat(), h.sexo)):
        beneficiarios.append(
            {
                "parentesco": "hijo",
                "sexo": hijo.sexo,
                "fecha_nacimiento": hijo.nacimiento.isoformat(),
                "invalidez": hijo.invalidez,
                "comun": hijo.comun,
            }
        )
    return beneficiarios


def build_detalle(
    *,
    actor_subject: str,
    role: str,
    tipo_escenario: str,
    version_modelo: str,
    codigo_verificacion: str,
    fecha_simulacion: date,
    saldo_uf: float,
    tasa_venta_pct: float,
    valor_uf: float | None,
    meses_garantizados: int,
    meses_aumento_temporal: int,
    pct_aumento_temporal: float,
    anios_diferidos: int,
    porcentaje_rvd: float,
    causante: Persona,
    conyuge: Persona | None,
    hijos: tuple[Hijo, ...],
    resultado: Resultado,
) -> dict[str, Any]:
    """Construye el ``detalle`` versionado (entradas + resultado + metadatos funcionales).

    Las entradas guardadas bastan para reproducir el resultado y el código de verificación
    (AC-3) y no contienen nombres, RUT, correo, teléfono ni el contenido del PDF (AC-2).
    """
    return {
        "schema_version": DETALLE_SCHEMA_VERSION,
        "actor_subject": actor_subject,
        "role": role,
        "tipo_escenario": tipo_escenario,
        "version_modelo": version_modelo,
        "codigo_verificacion": codigo_verificacion,
        "entradas": {
            "fecha_simulacion": fecha_simulacion.isoformat(),
            "saldo_uf": saldo_uf,
            "tasa_venta_pct": tasa_venta_pct,
            "valor_uf": valor_uf,
            "meses_garantizados": meses_garantizados,
            "meses_aumento_temporal": meses_aumento_temporal,
            "pct_aumento_temporal": pct_aumento_temporal,
            "anios_diferidos": anios_diferidos,
            "porcentaje_rvd": porcentaje_rvd,
            "causante": {
                "sexo": causante.sexo,
                "fecha_nacimiento": causante.nacimiento.isoformat(),
            },
            "beneficiarios": _beneficiarios(conyuge=conyuge, hijos=hijos),
        },
        "resultado": {
            "pension_uf": resultado.pension_mensual,
            "renta_temporal_uf": resultado.renta_temporal_mensual,
            "meses_diferidos": resultado.meses_diferidos,
        },
    }


def record_simulacion_event(
    *,
    id_lead: Any,
    actor_subject: str,
    role: str,
    tipo_escenario: str,
    version_modelo: str,
    codigo_verificacion: str,
    fecha_simulacion: date,
    saldo_uf: float,
    tasa_venta_pct: float,
    valor_uf: float | None,
    meses_garantizados: int,
    meses_aumento_temporal: int,
    pct_aumento_temporal: float,
    anios_diferidos: int,
    porcentaje_rvd: float,
    causante: Persona,
    conyuge: Persona | None,
    hijos: tuple[Hijo, ...],
    resultado: Resultado,
) -> None:
    """Inserta un evento append-only en ``tpi.auditoria`` para un PDF generado con éxito.

    ``detalle`` es JSON versionado con metadatos funcionales, las entradas y el resultado, sin
    PII directa. ``id_usuario``/``id_persona`` quedan ``NULL`` (no hay una identidad de usuario
    persistida para el backoffice web); ``id_lead`` identifica al lead simulado. La aplicación
    nunca lee ``tpi.auditoria`` directamente; es el mismo camino de escritura ya concedido a
    ``tpi_app`` por la migración 006 (sin cambio de esquema, clase A).
    """
    query = """
        INSERT INTO tpi.auditoria
            (id_usuario, id_persona, id_lead, accion, tabla_afectada, detalle)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    detalle = build_detalle(
        actor_subject=actor_subject,
        role=role,
        tipo_escenario=tipo_escenario,
        version_modelo=version_modelo,
        codigo_verificacion=codigo_verificacion,
        fecha_simulacion=fecha_simulacion,
        saldo_uf=saldo_uf,
        tasa_venta_pct=tasa_venta_pct,
        valor_uf=valor_uf,
        meses_garantizados=meses_garantizados,
        meses_aumento_temporal=meses_aumento_temporal,
        pct_aumento_temporal=pct_aumento_temporal,
        anios_diferidos=anios_diferidos,
        porcentaje_rvd=porcentaje_rvd,
        causante=causante,
        conyuge=conyuge,
        hijos=hijos,
        resultado=resultado,
    )
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
