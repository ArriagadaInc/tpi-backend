"""Unit tests for database health checks."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
import pytest

from app.config.settings import DatabaseConnectionConfig
from app.database import healthcheck


class FakeCursor:
    def __init__(self, fetchone_results: list[dict[str, Any]]) -> None:
        self.fetchone_results = fetchone_results
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def execute(self, query: Any, params: tuple[Any, ...] = ()) -> None:
        self.executed.append((str(query), params))

    def fetchone(self) -> dict[str, Any]:
        return self.fetchone_results.pop(0)

    def fetchall(self) -> list[dict[str, Any]]:
        return []


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_obj = cursor

    def cursor(self) -> FakeCursor:
        return self.cursor_obj


class FakeSettings:
    def __init__(self) -> None:
        self.database_schema = "tpi"
        self.normalized_app_env = "testing"
        self.database_config = DatabaseConnectionConfig(
            app_env="testing",
            source="database_fields",
            host="localhost",
            port=5432,
            database="tpi_test",
            user="tpi_app",
            password="test_password",
            schema="tpi",
            sslmode="disable",
            sslrootcert=None,
            connect_timeout=10,
            pool_min_size=1,
            pool_max_size=5,
            pool_timeout=30,
            application_name="tpi-test",
        )


@contextmanager
def fake_connection_context(
    conn: FakeConnection, operation: str = "ignored"
) -> Iterator[FakeConnection]:
    yield conn


def test_check_database_connection_reports_effective_user_and_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = FakeCursor(
        [
            {"ready": 1, "database_name": "tpi_test", "effective_user": "tpi_app"},
            {"schema_exists": True},
            {"table_exists": True},
        ]
    )
    conn = FakeConnection(cursor)

    monkeypatch.setattr(healthcheck, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(
        healthcheck,
        "get_db_connection",
        lambda operation="ignored": fake_connection_context(conn, operation),
    )

    result = healthcheck.check_database_connection()

    assert result["connected"] is True
    assert result["database"] == "tpi_test"
    assert result["effective_user"] == "tpi_app"
    assert result["schema_accessible"] is True
    assert result["leads_table_present"] is True
    assert result["leads_accessible"] is True


def test_check_database_connection_returns_safe_error_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(healthcheck, "get_settings", lambda: FakeSettings())

    @contextmanager
    def broken_connection(operation: str = "ignored") -> Iterator[FakeConnection]:
        raise psycopg.OperationalError('password authentication failed for user "tpi_app"')
        yield  # pragma: no cover

    monkeypatch.setattr(healthcheck, "get_db_connection", broken_connection)

    result = healthcheck.check_database_connection()

    assert result["connected"] is False
    assert result["error_code"] == "database_authentication_error"
    assert "credenciales" in result["message"].lower()
    assert "password authentication failed" in result["error"].lower()
