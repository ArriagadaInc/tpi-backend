"""List tables from the configured TPI schema using the shared DB layer."""

from __future__ import annotations

from app.config import get_settings
from app.database.connection import get_db_connection


def list_tables() -> bool:
    settings = get_settings()

    print("\n" + "=" * 70)
    print("VALIDACION: Tablas en esquema TPI")
    print("=" * 70)

    try:
        with get_db_connection(operation="root.list_tables") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = %s
                    ORDER BY table_name
                    """,
                    (settings.database_schema,),
                )
                tables = cur.fetchall()

                print(f"\nTablas encontradas: {len(tables)}")
                for row in tables:
                    table_name = row["table_name"]
                    cur.execute(f"SELECT COUNT(*) AS total FROM tpi.{table_name}")
                    count = cur.fetchone()["total"]
                    print(f"  - {table_name}: {count} registros")

        return True
    except Exception as exc:
        print(f"✗ Error: {exc}")
        return False


if __name__ == "__main__":
    list_tables()
