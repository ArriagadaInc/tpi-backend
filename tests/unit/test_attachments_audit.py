"""Pruebas del escritor de auditoría de adjuntos (AC-7), con conexión simulada."""

from __future__ import annotations

import json
from unittest.mock import patch

from app.attachments.audit import (
    ACCION_RECHAZADO,
    ACCION_SUBIDO,
    TABLA_AFECTADA,
    record_attachment_event,
)


def test_insert_append_only_with_verified_metadata() -> None:
    with patch("app.attachments.audit.get_db_connection") as gdb:
        conn = gdb.return_value.__enter__.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        record_attachment_event(
            accion=ACCION_SUBIDO,
            id_lead="11111111-1111-1111-1111-111111111111",
            actor_subject="subject-ceo",
            attachment_id="22222222-2222-2222-2222-222222222222",
            attachment_type="pdf",
            size=1024,
            sha256="a" * 64,
            archivos_incrustados=False,
        )

    sql, params = cur.execute.call_args.args
    assert "INSERT INTO tpi.auditoria" in sql
    assert params[0] is None  # id_usuario
    assert params[1] is None  # id_persona
    assert params[2] == "11111111-1111-1111-1111-111111111111"
    assert params[3] == ACCION_SUBIDO
    assert params[4] == TABLA_AFECTADA
    detalle = json.loads(params[5])
    assert detalle["actor_subject"] == "subject-ceo"
    assert detalle["adjunto_uuid"] == "22222222-2222-2222-2222-222222222222"
    assert detalle["tipo"] == "pdf"
    assert detalle["tamano"] == 1024
    assert detalle["sha256"] == "a" * 64
    assert detalle["codigo_rechazo"] is None
    assert detalle["archivos_incrustados"] is False


def test_rejection_detalle_carries_only_code_without_content() -> None:
    with patch("app.attachments.audit.get_db_connection") as gdb:
        conn = gdb.return_value.__enter__.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        record_attachment_event(
            accion=ACCION_RECHAZADO,
            id_lead="11111111-1111-1111-1111-111111111111",
            actor_subject="subject-ceo",
            attachment_id="",
            rejection_code="pdf_encrypted",
        )

    _sql, params = cur.execute.call_args.args
    detalle = json.loads(params[5])
    assert detalle["codigo_rechazo"] == "pdf_encrypted"
    assert detalle["tipo"] is None
    assert detalle["tamano"] is None
    assert detalle["sha256"] is None


def test_rollback_and_propagate_on_failure() -> None:
    with patch("app.attachments.audit.get_db_connection") as gdb:
        conn = gdb.return_value.__enter__.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.execute.side_effect = RuntimeError("db down")
        try:
            record_attachment_event(
                accion=ACCION_SUBIDO,
                id_lead="11111111-1111-1111-1111-111111111111",
                actor_subject="subject",
                attachment_id="22222222-2222-2222-2222-222222222222",
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("should propagate failure")
        conn.rollback.assert_called_once()
