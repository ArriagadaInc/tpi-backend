"""
Database-specific error types and safe message helpers.
"""

from __future__ import annotations

import re

import psycopg
from psycopg_pool import PoolTimeout

_DSN_PASSWORD_RE = re.compile(r"((?:postgres|postgresql)(?:\+psycopg)?://[^:\s]+:)([^@\s]+)(@)")
_CONNINFO_PASSWORD_RE = re.compile(r"(password=)([^\s]+)", re.IGNORECASE)


class DatabaseAppError(RuntimeError):
    """Base class for safe database errors."""

    code = "database_error"
    default_user_message = "No fue posible completar la operacion con la base de datos."

    def __init__(
        self,
        technical_message: str,
        *,
        operation: str,
        app_env: str | None = None,
        user_message: str | None = None,
        retryable: bool = False,
    ) -> None:
        sanitized_message = sanitize_exception_message(technical_message)
        super().__init__(sanitized_message)
        self.technical_message = sanitized_message
        self.operation = operation
        self.app_env = app_env
        self.user_message = user_message or self.default_user_message
        self.retryable = retryable


class DatabaseConfigurationError(DatabaseAppError):
    code = "database_configuration_error"
    default_user_message = (
        "La configuracion de conexion a la base de datos es incompleta o invalida."
    )


class DatabaseDnsError(DatabaseAppError):
    code = "database_dns_error"
    default_user_message = "No fue posible resolver el endpoint de la base de datos."
    retryable = True


class DatabaseTimeoutError(DatabaseAppError):
    code = "database_timeout"
    default_user_message = "La conexion a la base de datos excedio el tiempo de espera."
    retryable = True


class DatabaseAuthenticationError(DatabaseAppError):
    code = "database_authentication_error"
    default_user_message = "La base de datos rechazo las credenciales configuradas."


class DatabaseSSLError(DatabaseAppError):
    code = "database_ssl_error"
    default_user_message = "No fue posible establecer una conexion SSL valida con la base de datos."


class DatabasePoolExhaustedError(DatabaseAppError):
    code = "database_pool_exhausted"
    default_user_message = "No hay conexiones disponibles a la base de datos en este momento."
    retryable = True


class DatabaseUnavailableError(DatabaseAppError):
    code = "database_unavailable"
    default_user_message = "La base de datos no esta disponible en este momento."
    retryable = True


class DatabaseQueryError(DatabaseAppError):
    code = "database_query_error"
    default_user_message = "Ocurrio un error al ejecutar la operacion en la base de datos."


class DevLeadCleanupBlockedError(DatabaseAppError):
    """A DEV test lead has operational dependencies that prevent deletion."""

    code = "dev_test_lead_cleanup_blocked"
    default_user_message = "No fue posible eliminar el lead porque tiene referencias operacionales."


def sanitize_exception_message(message: str) -> str:
    """Redact passwords from URLs and conninfo strings before logging."""
    redacted = _DSN_PASSWORD_RE.sub(r"\1***\3", message)
    return _CONNINFO_PASSWORD_RE.sub(r"\1***", redacted)


def classify_database_exception(
    exc: Exception,
    *,
    operation: str,
    app_env: str | None = None,
) -> DatabaseAppError:
    """Map low-level exceptions to safe, typed database errors."""
    if isinstance(exc, DatabaseAppError):
        return exc

    technical_message = sanitize_exception_message(str(exc))
    lower_message = technical_message.lower()

    if isinstance(exc, PoolTimeout):
        return DatabasePoolExhaustedError(
            technical_message,
            operation=operation,
            app_env=app_env,
            retryable=True,
        )

    if isinstance(exc, ValueError) and "database_" in technical_message.lower():
        return DatabaseConfigurationError(
            technical_message,
            operation=operation,
            app_env=app_env,
        )

    if isinstance(exc, psycopg.OperationalError):
        if any(
            pattern in lower_message
            for pattern in (
                "could not translate host name",
                "name or service not known",
                "getaddrinfo failed",
                "nodename nor servname provided",
            )
        ):
            return DatabaseDnsError(
                technical_message,
                operation=operation,
                app_env=app_env,
                retryable=True,
            )

        if any(
            pattern in lower_message
            for pattern in (
                "timeout expired",
                "timed out",
                "connection timeout",
                "statement timeout",
            )
        ):
            return DatabaseTimeoutError(
                technical_message,
                operation=operation,
                app_env=app_env,
                retryable=True,
            )

        if any(
            pattern in lower_message
            for pattern in (
                "password authentication failed",
                "authentication failed",
                "invalid authorization specification",
            )
        ):
            return DatabaseAuthenticationError(
                technical_message,
                operation=operation,
                app_env=app_env,
            )

        if "ssl" in lower_message or "certificate" in lower_message:
            return DatabaseSSLError(
                technical_message,
                operation=operation,
                app_env=app_env,
            )

        if any(
            pattern in lower_message
            for pattern in (
                "connection refused",
                "could not connect to server",
                "server closed the connection unexpectedly",
                "the database system is starting up",
                "no route to host",
            )
        ):
            return DatabaseUnavailableError(
                technical_message,
                operation=operation,
                app_env=app_env,
                retryable=True,
            )

    if isinstance(exc, psycopg.Error):
        return DatabaseQueryError(
            technical_message,
            operation=operation,
            app_env=app_env,
        )

    return DatabaseAppError(
        technical_message,
        operation=operation,
        app_env=app_env,
    )


def get_safe_error_message(exc: Exception, *, fallback: str | None = None) -> str:
    """Return the message that can be displayed safely in Streamlit."""
    if isinstance(exc, DatabaseAppError):
        return exc.user_message

    if fallback:
        return fallback

    return "Ocurrio un error inesperado. Intenta nuevamente."
