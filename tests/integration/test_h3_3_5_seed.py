"""Real-PostgreSQL test for the H3.3.5 DEV advisor seed (never run against AWS DEV).

Executes the actual seed SQL (scripts/sql/dev/seed_asesores_desarrollo.sql) against
the ephemeral PostgreSQL test database, verifying idempotence, adopt-vs-abort, and
that other advisors stay intact. The seed's expected-database guard is overridden
via `SET tpi.seed_expected_database` (the same SQL defaults to `tpi` for DEV).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from psycopg import ClientCursor

from app.config import get_settings
from app.database.healthcheck import full_health_check

pytestmark = pytest.mark.integration

SEED_PATH = Path(__file__).parents[2] / "scripts" / "sql" / "dev" / "seed_asesores_desarrollo.sql"

A1 = "Asesor Desarrollo 1"
A2 = "Asesor Desarrollo 2"


@pytest.fixture(scope="session", autouse=True)
def verify_database() -> None:
    health = full_health_check()
    if not health.get("all_ready"):
        pytest.skip("Base de datos no disponible para tests de integración")


def _seed_sql() -> str:
    return SEED_PATH.read_text(encoding="utf-8")


def _connect() -> Any:
    return psycopg.connect(
        get_settings().get_database_url(),
        cursor_factory=ClientCursor,
    )


def _run_seed(conn: Any) -> None:
    db_name = conn.execute("SELECT current_database()").fetchone()[0]
    conn.execute(f"SET tpi.seed_expected_database = '{db_name}'")
    conn.execute(_seed_sql())


def _count_by_name(conn: Any, name: str) -> int:
    row = conn.execute(
        "SELECT count(*) FROM tpi.asesores WHERE lower(btrim(nombre)) = lower(btrim(%s))",
        (name,),
    ).fetchone()
    return int(row[0])


def _delete_by_name(conn: Any, name: str) -> None:
    conn.execute("DELETE FROM tpi.asesores WHERE lower(btrim(nombre)) = lower(btrim(%s))", (name,))


def _cleanup_names(conn: Any, names: tuple[str, ...]) -> None:
    for name in names:
        _delete_by_name(conn, name)
    conn.commit()


def test_seed_creates_both_advisors_and_is_idempotent() -> None:
    conn = _connect()
    try:
        _cleanup_names(conn, (A1, A2))

        _run_seed(conn)
        assert _count_by_name(conn, A1) == 1
        assert _count_by_name(conn, A2) == 1
        row = conn.execute(
            "SELECT rol, estado_disponibilidad FROM tpi.asesores "
            "WHERE lower(btrim(nombre)) = lower(btrim(%s))",
            (A1,),
        ).fetchone()
        assert row[0] == "asesor"
        assert row[1] == "activo"

        # Second execution produces the same result: no duplication.
        _run_seed(conn)
        assert _count_by_name(conn, A1) == 1
        assert _count_by_name(conn, A2) == 1
    finally:
        _cleanup_names(conn, (A1, A2))
        conn.close()


def test_seed_adopts_preexisting_compatible_record() -> None:
    conn = _connect()
    try:
        _cleanup_names(conn, (A1, A2))
        preexisting_id = uuid4()
        conn.execute(
            "INSERT INTO tpi.asesores (id_asesor, nombre, rol, estado_disponibilidad) "
            "VALUES (%s, %s, 'asesor', 'activo')",
            (str(preexisting_id), A1),
        )
        conn.commit()

        _run_seed(conn)

        # Adopted (no duplicate), and the pre-existing UUID is preserved.
        assert _count_by_name(conn, A1) == 1
        row = conn.execute(
            "SELECT id_asesor FROM tpi.asesores WHERE lower(btrim(nombre)) = lower(btrim(%s))",
            (A1,),
        ).fetchone()
        assert str(row[0]) == str(preexisting_id)
        assert _count_by_name(conn, A2) == 1
    finally:
        _cleanup_names(conn, (A1, A2))
        conn.close()


def test_seed_aborts_on_incompatible_record_without_partial_write() -> None:
    conn = _connect()
    try:
        _cleanup_names(conn, (A1, A2))
        conn.execute(
            "INSERT INTO tpi.asesores (nombre, rol, estado_disponibilidad) "
            "VALUES (%s, 'gerente', 'activo')",
            (A1,),
        )
        conn.commit()

        with pytest.raises(psycopg.errors.RaiseException):
            _run_seed(conn)
        conn.rollback()

        # The whole transaction rolled back: neither advisor was written.
        assert _count_by_name(conn, A1) == 1  # the incompatible pre-existing row
        assert _count_by_name(conn, A2) == 0
    finally:
        _cleanup_names(conn, (A1, A2))
        conn.close()


def test_seed_leaves_other_advisors_intact() -> None:
    conn = _connect()
    try:
        _cleanup_names(conn, (A1, A2))
        other_name = f"Asesor Ajeno {uuid4().hex[:12]}"
        conn.execute(
            "INSERT INTO tpi.asesores (nombre, rol, estado_disponibilidad) "
            "VALUES (%s, 'asesor', 'activo')",
            (other_name,),
        )
        conn.commit()

        _run_seed(conn)

        assert _count_by_name(conn, A1) == 1
        assert _count_by_name(conn, A2) == 1
        # The unrelated advisor was not modified or duplicated.
        assert _count_by_name(conn, other_name) == 1
        row = conn.execute(
            "SELECT estado_disponibilidad FROM tpi.asesores "
            "WHERE lower(btrim(nombre)) = lower(btrim(%s))",
            (other_name,),
        ).fetchone()
        assert row[0] == "activo"
    finally:
        _cleanup_names(conn, (A1, A2))
        conn.execute(
            "DELETE FROM tpi.asesores WHERE lower(btrim(nombre)) = lower(btrim(%s))", (other_name,)
        )
        conn.commit()
        conn.close()
