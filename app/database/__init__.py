"""Módulo de base de datos."""

from app.database.connection import (
    initialize_pool,
    close_pool,
    get_db_connection,
    execute_query,
    execute_insert,
)
from app.database.healthcheck import (
    check_database_connection,
    check_schema_exists,
    check_required_tables,
    check_catalogs,
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
