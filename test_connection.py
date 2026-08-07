"""Quick connectivity smoke test using the centralized database layer."""

from __future__ import annotations

import sys

from app.config import get_settings
from app.database.connection import get_db_connection


def test_database_connection() -> bool:
    settings = get_settings()
    config = settings.database_config

    print("\n" + "=" * 70)
    print("VALIDACION 1: Conexion a PostgreSQL")
    print("=" * 70)
    print(f"Host: {config.host}:{config.port}")
    print(f"Base de datos: {config.database}")
    print(f"Usuario esperado: {config.user}")
    print(f"SSL: {config.sslmode}")

    try:
        with get_db_connection(operation="root.test_connection.ping") as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version(), current_user")
                row = cur.fetchone()
                print("✓ Conexion exitosa a PostgreSQL")
                print(f"✓ {str(row['version']).split(',')[0]}")
                print(f"✓ Usuario efectivo: {row['current_user']}")
        return True
    except Exception as exc:
        print(f"✗ Error de conexion: {type(exc).__name__}")
        print(f"  Detalle: {exc}")
        return False


def test_core_tables() -> bool:
    print("\n" + "=" * 70)
    print("VALIDACION 2: Tablas Core del Backoffice")
    print("=" * 70)

    required_tables = ["personas", "leads", "consentimientos"]

    try:
        with get_db_connection(operation="root.test_connection.tables") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'tpi'
                      AND table_name = ANY(%s)
                    ORDER BY table_name
                    """,
                    (required_tables,),
                )
                found_tables = [row["table_name"] for row in cur.fetchall()]

                print(f"✓ Tablas encontradas: {len(found_tables)} de {len(required_tables)}")
                for table_name in found_tables:
                    cur.execute(f"SELECT COUNT(*) AS total FROM tpi.{table_name}")
                    count = cur.fetchone()["total"]
                    print(f"  ✓ {table_name}: {count} registros")

        return len(found_tables) == len(required_tables)
    except Exception as exc:
        print(f"✗ Error: {exc}")
        return False


if __name__ == "__main__":
    success1 = test_database_connection()
    success2 = test_core_tables()

    if success1 and success2:
        print("\n" + "=" * 70)
        print("✓ Todas las validaciones de conexion pasaron")
        print("=" * 70 + "\n")
        sys.exit(0)

    print("\n" + "=" * 70)
    print("✗ Algunas validaciones fallaron")
    print("=" * 70 + "\n")
    sys.exit(1)
