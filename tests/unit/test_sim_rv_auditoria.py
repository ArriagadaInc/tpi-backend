"""Escritor del evento de auditoría del simulador (AC-11 y SIM-EVIDENCIA-ENTRADAS), con conexión simulada."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

import pytest

from app.services.simulador_auditoria import (
    ACCION_SIMULACION,
    DETALLE_SCHEMA_VERSION,
    TABLA_AFECTADA,
    record_simulacion_event,
)
from app.simulador_pension import Hijo, Persona, Resultado


def _resultado() -> Resultado:
    return Resultado(
        pension_mensual=12.34,
        pension_exacta=12.345678,
        prima_uf=2800.0,
        prima_neta_afp_uf=200.0,
        cnu=220.0,
    )


def _entradas_kwargs() -> dict[str, object]:
    return {
        "fecha_simulacion": date(2026, 10, 16),
        "saldo_uf": 3000.0,
        "tasa_venta_pct": 4.7,
        "valor_uf": 38000.0,
        "meses_garantizados": 120,
        "meses_aumento_temporal": 24,
        "pct_aumento_temporal": 10.0,
        "anios_diferidos": 0,
        "porcentaje_rvd": 100.0,
        "causante": Persona("H", date(1960, 1, 15)),
        "conyuge": Persona("M", date(1962, 5, 20)),
        "hijos": (
            Hijo("M", date(2000, 3, 10), comun=True, invalidez="no"),
            Hijo("H", date(1998, 7, 1), comun=False, invalidez="parcial"),
        ),
        "resultado": _resultado(),
    }


def test_insert_append_only_con_evidencia_versionada() -> None:
    kwargs = _entradas_kwargs()
    with patch("app.services.simulador_auditoria.get_db_connection") as gdb:
        conn = gdb.return_value.__enter__.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        record_simulacion_event(
            id_lead="11111111-1111-1111-1111-111111111111",
            actor_subject="subject-executive",
            role="executive",
            tipo_escenario="renta_inmediata_familia",
            version_modelo="1.0.0",
            codigo_verificacion="0123456789ab",
            **kwargs,
        )

    sql, params = cur.execute.call_args.args
    assert "INSERT INTO tpi.auditoria" in sql
    assert params[0] is None  # id_usuario
    assert params[1] is None  # id_persona
    assert params[2] == "11111111-1111-1111-1111-111111111111"  # id_lead
    assert params[3] == ACCION_SIMULACION
    assert params[4] == TABLA_AFECTADA
    detalle = json.loads(params[5])
    assert detalle["schema_version"] == DETALLE_SCHEMA_VERSION
    assert detalle["actor_subject"] == "subject-executive"
    assert detalle["role"] == "executive"
    assert detalle["tipo_escenario"] == "renta_inmediata_familia"
    assert detalle["version_modelo"] == "1.0.0"
    assert detalle["codigo_verificacion"] == "0123456789ab"

    entradas = detalle["entradas"]
    assert entradas["fecha_simulacion"] == "2026-10-16"
    assert entradas["saldo_uf"] == 3000.0
    assert entradas["tasa_venta_pct"] == 4.7
    assert entradas["valor_uf"] == 38000.0
    assert entradas["meses_garantizados"] == 120
    assert entradas["meses_aumento_temporal"] == 24
    assert entradas["pct_aumento_temporal"] == 10.0
    assert entradas["anios_diferidos"] == 0
    assert entradas["porcentaje_rvd"] == 100.0
    assert entradas["causante"] == {"sexo": "H", "fecha_nacimiento": "1960-01-15"}
    # Hijos ordenados por (fecha de nacimiento, sexo); cónyuge primero.
    assert entradas["beneficiarios"] == [
        {
            "parentesco": "conyuge",
            "sexo": "M",
            "fecha_nacimiento": "1962-05-20",
            "invalidez": None,
            "comun": None,
        },
        {
            "parentesco": "hijo",
            "sexo": "H",
            "fecha_nacimiento": "1998-07-01",
            "invalidez": "parcial",
            "comun": False,
        },
        {
            "parentesco": "hijo",
            "sexo": "M",
            "fecha_nacimiento": "2000-03-10",
            "invalidez": "no",
            "comun": True,
        },
    ]
    assert detalle["resultado"] == {
        "pension_uf": 12.34,
        "renta_temporal_uf": None,
        "meses_diferidos": 0,
    }
    conn.commit.assert_called_once()


def test_detalle_sin_nombres_ni_pii() -> None:
    """El detalle serializado no lleva nombres, RUT, correo, teléfono ni contenido del PDF."""
    kwargs = _entradas_kwargs()
    with patch("app.services.simulador_auditoria.get_db_connection") as gdb:
        conn = gdb.return_value.__enter__.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        record_simulacion_event(
            id_lead="L1",
            actor_subject="subject-executive",
            role="executive",
            tipo_escenario="renta_inmediata_familia",
            version_modelo="1.0.0",
            codigo_verificacion="0123456789ab",
            **kwargs,
        )
    detalle = json.loads(cur.execute.call_args.args[1][5])
    serialized = json.dumps(detalle, ensure_ascii=False)
    for prohibido in (
        "nombre",
        "Nombre",
        "RUT",
        "rut",
        "correo",
        "email",
        "telefono",
        "teléfono",
        "12.345.678-5",
        "@",
        "+56",
    ):
        assert prohibido not in serialized
    # El contenido del PDF (nombre del cliente y contacto corporativo) tampoco aparece.
    assert "Juan" not in serialized
    assert "Estudio de pensión" not in serialized
    assert "contacto@tupensioninteligente.cl" not in serialized


def test_rollback_y_propaga_fallo() -> None:
    kwargs = _entradas_kwargs()
    with patch("app.services.simulador_auditoria.get_db_connection") as gdb:
        conn = gdb.return_value.__enter__.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.execute.side_effect = RuntimeError("db down")
        with pytest.raises(RuntimeError):
            record_simulacion_event(
                id_lead="L1",
                actor_subject="s",
                role="executive",
                tipo_escenario="renta_inmediata_causante",
                version_modelo="1.0.0",
                codigo_verificacion="abc",
                **kwargs,
            )
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
