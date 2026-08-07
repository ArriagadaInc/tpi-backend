"""Database layer exports."""

from app.database.connection import (
    close_pool,
    execute_insert,
    execute_query,
    get_connection,
    get_db_connection,
    initialize_pool,
    reset_pool,
)
from app.database.errors import (
    DatabaseAppError,
    DatabaseAuthenticationError,
    DatabaseConfigurationError,
    DatabaseDnsError,
    DatabasePoolExhaustedError,
    DatabaseQueryError,
    DatabaseSSLError,
    DatabaseTimeoutError,
    DatabaseUnavailableError,
    classify_database_exception,
    get_safe_error_message,
)
from app.database.healthcheck import (
    check_catalogs,
    check_database_connection,
    check_required_tables,
    check_schema_exists,
    full_health_check,
)

__all__ = [
    "DatabaseAppError",
    "DatabaseAuthenticationError",
    "DatabaseConfigurationError",
    "DatabaseDnsError",
    "DatabasePoolExhaustedError",
    "DatabaseQueryError",
    "DatabaseSSLError",
    "DatabaseTimeoutError",
    "DatabaseUnavailableError",
    "classify_database_exception",
    "get_safe_error_message",
    "initialize_pool",
    "close_pool",
    "reset_pool",
    "get_connection",
    "get_db_connection",
    "execute_query",
    "execute_insert",
    "check_database_connection",
    "check_schema_exists",
    "check_required_tables",
    "check_catalogs",
    "full_health_check",
]
