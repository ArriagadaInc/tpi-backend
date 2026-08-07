"""Administrative PostgreSQL user inspection using shared configuration."""

from __future__ import annotations

import psycopg

from app.config import get_settings


def check_postgres_users() -> bool:
    print("\n" + "=" * 70)
    print("VERIFICACION: Usuarios de PostgreSQL")
    print("=" * 70)

    try:
        config = get_settings().database_config
        params = config.connection_parameters()
        params["dbname"] = "postgres"

        with psycopg.connect(**params) as conn:
            print("✓ Conexion administrativa exitosa")

            result = conn.execute("SELECT usename, usesuper FROM pg_user ORDER BY usename").fetchall()
            print(f"\nUsuarios en PostgreSQL ({len(result)} total):")
            for row in result:
                super_flag = "SUPERUSER" if row[1] else ""
                print(f"  - {row[0]} {super_flag}".rstrip())

            result = conn.execute(
                "SELECT datname FROM pg_database WHERE datname NOT LIKE 'template%' ORDER BY datname"
            ).fetchall()
            print(f"\nBases de datos ({len(result)} total):")
            for row in result:
                print(f"  - {row[0]}")

        return True
    except Exception as exc:
        print(f"✗ Error: {exc}")
        print("  Nota: este script requiere acceso administrativo a la base 'postgres'.")
        return False


if __name__ == "__main__":
    check_postgres_users()
