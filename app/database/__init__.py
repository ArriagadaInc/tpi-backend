"""Módulo de base de datos."""

from app.database.connection import (
    close_pool,
    execute_insert,
    execute_query,
    get_db_connection,
    initialize_pool,
)
from app.database.healthcheck import (
    check_catalogs,
    check_database_connection,
    check_required_tables,
    check_schema_exists,
    full_health_check,
)

__all__ = [
    "initialize_pool",
    "close_pool",
    "get_db_connection",
    "execute_query",
    "execute_insert",
    "check_database_connection",
    "check_schema_exists",
    "check_required_tables",
    "check_catalogs",
    "full_health_check",
]
