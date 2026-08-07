"""
PostgreSQL connection and pool management.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from threading import Lock
from typing import Any, cast

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config.settings import DatabaseConnectionConfig, get_settings
from app.database.errors import DatabaseAppError, classify_database_exception

logger = logging.getLogger(__name__)

DbRow = dict[str, Any]
DbConnection = psycopg.Connection[DbRow]

_connection_pool: ConnectionPool[DbConnection] | None = None
_pool_signature: tuple[str, ...] | None = None
_pool_lock = Lock()


def _get_database_config() -> DatabaseConnectionConfig:
    settings = get_settings()

    try:
        return settings.database_config
    except Exception as exc:  # pragma: no cover - exercised via callers
        raise classify_database_exception(
            exc,
            operation="database_config",
            app_env=settings.normalized_app_env,
        ) from exc


def _log_database_error(operation: str, error: DatabaseAppError) -> None:
    logger.error(
        "Database operation failed | env=%s | operation=%s | code=%s | detail=%s",
        error.app_env or "unknown",
        operation,
        error.code,
        error.technical_message,
    )


def _build_pool(config: DatabaseConnectionConfig) -> ConnectionPool[DbConnection]:
    pool = ConnectionPool(
        conninfo=config.conninfo(),
        kwargs={"row_factory": dict_row},
        min_size=config.pool_min_size,
        max_size=config.pool_max_size,
        timeout=float(config.pool_timeout),
        name=f"tpi-backoffice-{config.app_env}",
        open=False,
    )
    pool.open(wait=True, timeout=float(config.pool_timeout))
    return cast("ConnectionPool[DbConnection]", pool)


def initialize_pool(force: bool = False) -> None:
    """
    Initialize the shared connection pool.

    The pool is reused across Streamlit reruns inside the same process.
    """

    global _connection_pool, _pool_signature

    config = _get_database_config()
    desired_signature = config.pool_signature()

    with _pool_lock:
        if _connection_pool is not None and _pool_signature == desired_signature and not force:
            return

        if _connection_pool is not None:
            _connection_pool.close()
            _connection_pool = None
            _pool_signature = None

        try:
            _connection_pool = _build_pool(config)
            _pool_signature = desired_signature
            logger.info(
                "Database pool initialized | env=%s | target=%s:%s/%s | sslmode=%s | pool=%s-%s",
                config.app_env,
                config.host,
                config.port,
                config.database,
                config.sslmode,
                config.pool_min_size,
                config.pool_max_size,
            )
        except Exception as exc:
            error = classify_database_exception(
                exc,
                operation="initialize_pool",
                app_env=config.app_env,
            )
            _log_database_error("initialize_pool", error)
            raise error from exc


def close_pool() -> None:
    """Close the shared connection pool."""

    global _connection_pool, _pool_signature

    with _pool_lock:
        if _connection_pool is None:
            return

        _connection_pool.close()
        _connection_pool = None
        _pool_signature = None
        logger.info("Database pool closed")


def reset_pool() -> None:
    """Alias used by tests to reset module state."""
    close_pool()


def get_connection(timeout: float | None = None) -> DbConnection:
    """Acquire a connection from the shared pool."""

    initialize_pool()
    pool = _connection_pool

    if pool is None:
        raise RuntimeError("The database connection pool is not initialized")

    config = _get_database_config()

    try:
        return cast("ConnectionPool[DbConnection]", pool).getconn(timeout=timeout)
    except Exception as exc:
        error = classify_database_exception(
            exc,
            operation="get_connection",
            app_env=config.app_env,
        )
        _log_database_error("get_connection", error)
        raise error from exc


def return_connection(conn: DbConnection) -> None:
    """Return a connection to the pool, or close it if the pool no longer exists."""
    pool = _connection_pool

    if pool is None:
        conn.close()
        return

    try:
        pool.putconn(conn)
    except Exception:
        conn.close()
        raise


def _reset_connection_state(conn: DbConnection) -> None:
    try:
        if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
            conn.rollback()
    except Exception:
        conn.close()


@contextmanager
def get_db_connection(operation: str = "database_operation") -> Generator[DbConnection, None, None]:
    """
    Context manager returning a pooled psycopg connection.

    Any open transaction is rolled back before the connection returns to the pool.
    """

    conn: DbConnection | None = None

    try:
        conn = get_connection()
        yield conn
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                conn.close()

        error = classify_database_exception(
            exc,
            operation=operation,
            app_env=get_settings().normalized_app_env,
        )
        _log_database_error(operation, error)
        raise error from exc
    finally:
        if conn is not None:
            _reset_connection_state(conn)
            return_connection(conn)


def execute_query(
    query: str,
    params: tuple[Any, ...] | None = None,
    *,
    fetch_one: bool = False,
) -> DbRow | list[DbRow] | None:
    """Execute a parameterized SELECT statement safely."""
    with get_db_connection(operation="execute_query") as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            if fetch_one:
                return cur.fetchone()
            return cur.fetchall()


def execute_insert(
    query: str,
    params: tuple[Any, ...] | None = None,
    *,
    return_id: bool = False,
) -> DbRow | None:
    """Execute a parameterized INSERT statement with commit-on-success."""
    with get_db_connection(operation="execute_insert") as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            result = cur.fetchone() if return_id else None
            conn.commit()
            return result
