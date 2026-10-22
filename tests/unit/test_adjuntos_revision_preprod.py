"""Pruebas del script de medición de adjuntos (CRM-ADJUNTOS-REVISION-PREPROD, AC-3).

Verifican con una conexión simulada que todo el SQL es de solo lectura, que los
parámetros van como parámetros (no interpolados), que los agregados son correctos
y que la salida no expone PII ni identificadores.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts.adjuntos_revision_preprod import build_queries, main, render, run_queries

FORBIDDEN_DML_DDL = (
    "insert",
    "update",
    "delete",
    "create",
    "alter",
    "drop",
    "truncate",
    "grant",
    "revoke",
    "merge",
    "call",
    "copy",
    "execute",
    "prepare",
)


def test_all_queries_are_select_only_and_parameterized() -> None:
    for metrica in build_queries(30):
        sql_normalizado = " ".join(metrica.sql.split()).lower()
        assert sql_normalizado.startswith("select"), metrica.clave
        for word in FORBIDDEN_DML_DDL:
            assert word not in sql_normalizado, (metrica.clave, word)
        # Una sola sentencia y con marcador de parámetro.
        assert ";" not in metrica.sql
        assert "%s" in metrica.sql


def test_days_is_parameterized_not_interpolated() -> None:
    for metrica in build_queries(37):
        assert metrica.params[0] == "tpi.leads"
        assert metrica.params[1] == 37
        assert "37" not in metrica.sql
        # El nombre de la tabla también viaja como parámetro, no en el texto.
        assert "tpi.leads" not in metrica.sql


def test_run_queries_uses_cursor_and_parameters() -> None:
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    queries = build_queries(30)
    cur.fetchall.side_effect = [[{"accion": "adjunto_subido", "total": 1}]] * len(queries)

    resultados = run_queries(conn, queries)

    assert set(resultados.keys()) == {metrica.clave for metrica in queries}
    calls = [call.args for call in cur.execute.call_args_list]
    for (sql, params), metrica in zip(calls, queries):
        assert sql == metrica.sql
        assert params == metrica.params


def test_render_shows_aggregates_only_without_pii() -> None:
    resultados = {
        "conteo_por_accion": [
            {"accion": "adjunto_subido", "total": 12},
            {"accion": "adjunto_rechazado", "total": 3},
            {"accion": "adjunto_visto", "total": 40},
            {"accion": "adjunto_descargado", "total": 5},
            {"accion": "adjunto_eliminado", "total": 1},
        ],
        "rechazos_por_codigo": [{"codigo": "pdf_encrypted", "total": 2}],
        "subidas_incrustados": [
            {"categoria": "sin_archivos_incrustados", "total": 10},
            {"categoria": "con_archivos_incrustados", "total": 2},
        ],
        "subidas_por_tipo": [
            {"tipo": "pdf", "total": 8},
            {"tipo": "png", "total": 4},
        ],
        "objetos_bytes_por_mes": [{"mes": "2026-09", "objetos": 12, "bytes": 1048576}],
        "agregados_generales": [{"leads_con_adjuntos": 10, "usuarios_que_subieron": 4}],
    }

    salida = render(resultados, 30)

    assert "accion=adjunto_subido" in salida
    assert "codigo=pdf_encrypted" in salida
    assert "categoria=con_archivos_incrustados" in salida
    assert "tipo=pdf" in salida
    assert "1.00 MiB" in salida
    assert "leads distintos con adjuntos: 10" in salida
    assert "usuarios distintos que subieron: 4" in salida

    # Nada de PII, contenido, SHA-256 ni identificadores de lead o persona.
    minusculas = salida.lower()
    for prohibido in ("sha256", "actor_subject", "rut", "uuid", "@", "adjunto_uuid"):
        assert prohibido not in minusculas


def test_render_empty_window_has_no_rows() -> None:
    salida = render({}, 30)
    assert "(sin eventos en la ventana)" in salida
    assert "(sin subidas en la ventana)" in salida


def test_main_returns_nonzero_when_connection_fails() -> None:
    with patch("scripts.adjuntos_revision_preprod.get_db_connection") as gdb:
        gdb.side_effect = RuntimeError("db down")
        code = main(["--days", "30"])
    assert code == 1


def test_main_rejects_nonpositive_days() -> None:
    assert main(["--days", "0"]) == 2
    assert main(["--days", "-5"]) == 2
