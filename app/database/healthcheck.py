"""
Database health checks for connectivity and application readiness.
"""

from __future__ import annotations

import logging
from typing import Any

from psycopg import sql

from app.config.settings import get_settings
from app.database.connection import get_db_connection
from app.database.errors import DatabaseAppError, classify_database_exception

logger = logging.getLogger(__name__)


def _log_health_error(operation: str, error: DatabaseAppError) -> None:
    logger.error(
        "Database health check failed | env=%s | operation=%s | code=%s | detail=%s",
        error.app_env or "unknown",
        operation,
        error.code,
        error.technical_message,
    )


def check_database_connection() -> dict[str, Any]:
    """
    Verify connectivity, schema visibility, table visibility, and effective user.
    """

    settings = get_settings()
    schema_name = settings.database_schema

    try:
        config = settings.database_config
        with get_db_connection(operation="healthcheck.connection") as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        1 AS ready,
                        current_database() AS database_name,
                        current_user AS effective_user
                    """)
                connection_row = cur.fetchone() or {}

                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.schemata
                        WHERE schema_name = %s
                    ) AS schema_exists
                    """,
                    (schema_name,),
                )
                schema_row = cur.fetchone() or {}
                schema_accessible = bool(schema_row.get("schema_exists"))

                table_names = ("leads", "asesores", "asignaciones")
                table_presence: dict[str, bool] = {}
                table_accessibility: dict[str, bool] = {}

                for table_name in table_names:
                    cur.execute(
                        "SELECT to_regclass(%s) IS NOT NULL AS table_exists",
                        (f"{schema_name}.{table_name}",),
                    )
                    table_row = cur.fetchone() or {}
                    table_present = bool(table_row.get("table_exists"))
                    table_presence[table_name] = table_present
                    table_accessibility[table_name] = False

                    if table_present:
                        cur.execute(
                            sql.SQL("SELECT 1 FROM {}.{} WHERE 1 = 0").format(
                                sql.Identifier(schema_name),
                                sql.Identifier(table_name),
                            )
                        )
                        table_accessibility[table_name] = True

        return {
            "connected": connection_row.get("ready") == 1,
            "message": "Base de datos conectada correctamente",
            "error": None,
            "error_code": None,
            "database": connection_row.get("database_name", config.database),
            "schema": schema_name,
            "effective_user": connection_row.get("effective_user"),
            "schema_accessible": schema_accessible,
            "leads_table_present": table_presence["leads"],
            "leads_accessible": table_accessibility["leads"],
            "asesores_table_present": table_presence["asesores"],
            "asesores_accessible": table_accessibility["asesores"],
            "asignaciones_table_present": table_presence["asignaciones"],
            "asignaciones_accessible": table_accessibility["asignaciones"],
            "sslmode": config.sslmode,
        }

    except Exception as exc:
        error = classify_database_exception(
            exc,
            operation="healthcheck.connection",
            app_env=settings.normalized_app_env,
        )
        _log_health_error("healthcheck.connection", error)
        return {
            "connected": False,
            "message": error.user_message,
            "error": error.technical_message,
            "error_code": error.code,
            "database": None,
            "schema": schema_name,
            "effective_user": None,
            "schema_accessible": False,
            "leads_table_present": False,
            "leads_accessible": False,
            "asesores_table_present": False,
            "asesores_accessible": False,
            "asignaciones_table_present": False,
            "asignaciones_accessible": False,
            "sslmode": None,
        }


def check_schema_exists() -> dict[str, Any]:
    """Verify that the configured schema exists and contains tables."""
    settings = get_settings()

    try:
        with get_db_connection(operation="healthcheck.schema") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM information_schema.tables
                    WHERE table_schema = %s
                    """,
                    (settings.database_schema,),
                )
                row = cur.fetchone() or {}
                tables_count = int(row.get("count", 0))

        return {
            "exists": tables_count > 0,
            "message": f"Schema '{settings.database_schema}' with {tables_count} tables",
            "tables_count": tables_count,
        }

    except Exception as exc:
        error = classify_database_exception(
            exc,
            operation="healthcheck.schema",
            app_env=settings.normalized_app_env,
        )
        _log_health_error("healthcheck.schema", error)
        return {
            "exists": False,
            "message": error.user_message,
            "tables_count": 0,
        }


def check_required_tables() -> dict[str, Any]:
    """Verify that the MVP-required tables are present."""
    settings = get_settings()
    required_tables = [
        "personas",
        "leads",
        "asesores",
        "asignaciones",
        "consentimientos",
        "catalogo_afp",
        "catalogo_genero",
        "catalogo_estado_civil",
    ]

    try:
        with get_db_connection(operation="healthcheck.required_tables") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = %s
                    """,
                    (settings.database_schema,),
                )
                existing_tables = {row["table_name"] for row in cur.fetchall()}

        found = [table_name for table_name in required_tables if table_name in existing_tables]
        missing = [
            table_name for table_name in required_tables if table_name not in existing_tables
        ]

        return {
            "all_present": not missing,
            "required": required_tables,
            "found": found,
            "missing": missing,
        }

    except Exception as exc:
        error = classify_database_exception(
            exc,
            operation="healthcheck.required_tables",
            app_env=settings.normalized_app_env,
        )
        _log_health_error("healthcheck.required_tables", error)
        return {
            "all_present": False,
            "required": required_tables,
            "found": [],
            "missing": required_tables,
        }


def check_catalogs() -> dict[str, Any]:
    """Verify that required catalogs contain active data."""
    settings = get_settings()

    try:
        with get_db_connection(operation="healthcheck.catalogs") as conn:
            with conn.cursor() as cur:
                catalog_tables = {
                    "afp_count": "catalogo_afp",
                    "genero_count": "catalogo_genero",
                    "estado_civil_count": "catalogo_estado_civil",
                }
                results: dict[str, int] = {}

                for key, table_name in catalog_tables.items():
                    cur.execute(
                        sql.SQL("SELECT COUNT(*) AS count FROM {}.{} WHERE activo = TRUE").format(
                            sql.Identifier(settings.database_schema),
                            sql.Identifier(table_name),
                        )
                    )
                    row = cur.fetchone() or {}
                    results[key] = int(row.get("count", 0))

        return {
            "all_ready": all(value > 0 for value in results.values()),
            **results,
        }

    except Exception as exc:
        error = classify_database_exception(
            exc,
            operation="healthcheck.catalogs",
            app_env=settings.normalized_app_env,
        )
        _log_health_error("healthcheck.catalogs", error)
        return {
            "all_ready": False,
            "afp_count": 0,
            "genero_count": 0,
            "estado_civil_count": 0,
        }


def full_health_check() -> dict[str, Any]:
    """
    Execute a complete health check for the backoffice database dependencies.
    """

    connection = check_database_connection()
    schema = check_schema_exists()
    tables = check_required_tables()
    catalogs = check_catalogs()

    all_ready = (
        connection["connected"]
        and connection["schema_accessible"]
        and connection["leads_accessible"]
        and schema["exists"]
        and tables["all_present"]
        and catalogs["all_ready"]
    )

    return {
        "all_ready": all_ready,
        "connected": connection["connected"],
        "connection": connection,
        "schema": schema,
        "tables": tables,
        "catalogs": catalogs,
    }
