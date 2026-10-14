"""Escritor del evento de auditoría del simulador (AC-11), con conexión simulada."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.services.simulador_auditoria import (
    ACCION_SIMULACION,
    TABLA_AFECTADA,
    record_simulacion_event,
)


def test_insert_append_only_sin_pii() -> None:
    with patch("app.services.simulador_auditoria.get_db_connection") as gdb:
        conn = gdb.return_value.__enter__.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        record_simulacion_event(
            id_lead="11111111-1111-1111-1111-111111111111",
            actor_subject="subject-executive",
            role="executive",
            tipo_escenario="renta_inmediata_causante",
            version_modelo="1.0.0",
            codigo_verificacion="0123456789ab",
        )

    sql, params = cur.execute.call_args.args
    assert "INSERT INTO tpi.auditoria" in sql
    assert params[0] is None  # id_usuario
    assert params[1] is None  # id_persona
    assert params[2] == "11111111-1111-1111-1111-111111111111"  # id_lead
    assert params[3] == ACCION_SIMULACION
    assert params[4] == TABLA_AFECTADA
    detalle = json.loads(params[5])
    assert detalle == {
        "actor_subject": "subject-executive",
        "role": "executive",
        "tipo_escenario": "renta_inmediata_causante",
        "version_modelo": "1.0.0",
        "codigo_verificacion": "0123456789ab",
    }
    conn.commit.assert_called_once()


def test_rollback_y_propaga_fallo() -> None:
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
            )
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
