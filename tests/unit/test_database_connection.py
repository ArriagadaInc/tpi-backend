"""Unit tests for connection pool lifecycle and transaction handling."""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from app.config.settings import DatabaseConnectionConfig
from app.database import DatabaseAppError
from app.database import connection as connection_module


class FakeInfo:
    def __init__(self) -> None:
        self.transaction_status = psycopg.pq.TransactionStatus.IDLE


class FakeCursor:
    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.result = result or {"id": 123}
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def execute(self, query: str, params: tuple[Any, ...]) -> None:
        self.executed.append((query, params))

    def fetchone(self) -> dict[str, Any]:
        return self.result

    def fetchall(self) -> list[dict[str, Any]]:
        return [self.result]


class FakeConnection:
    def __init__(self, cursor: FakeCursor | None = None) -> None:
        self.cursor_obj = cursor or FakeCursor()
        self.commit_called = False
        self.rollback_called = False
        self.closed = False
        self.info = FakeInfo()

    def cursor(self) -> FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.commit_called = True

    def rollback(self) -> None:
        self.rollback_called = True
        self.info.transaction_status = psycopg.pq.TransactionStatus.IDLE

    def close(self) -> None:
        self.closed = True


class FakePool:
    instances: list[FakePool] = []

    def __init__(self, *_: Any, **__: Any) -> None:
        self.connection = FakeConnection()
        self.open_calls: list[tuple[bool, float]] = []
        self.getconn_calls: list[float | None] = []
        self.returned_connection: FakeConnection | None = None
        self.closed = False
        FakePool.instances.append(self)

    def open(self, wait: bool = False, timeout: float = 30.0) -> None:
        self.open_calls.append((wait, timeout))

    def close(self) -> None:
        self.closed = True

    def getconn(self, timeout: float | None = None) -> FakeConnection:
        self.getconn_calls.append(timeout)
        return self.connection

    def putconn(self, conn: FakeConnection) -> None:
        self.returned_connection = conn


class FakeSettings:
    def __init__(self, config: DatabaseConnectionConfig) -> None:
        self.database_config = config
        self.normalized_app_env = config.app_env


def make_config() -> DatabaseConnectionConfig:
    return DatabaseConnectionConfig(
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


def test_initialize_pool_only_once_for_same_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakePool.instances.clear()
    connection_module.reset_pool()
    monkeypatch.setattr(connection_module, "ConnectionPool", FakePool)
    monkeypatch.setattr(connection_module, "get_settings", lambda: FakeSettings(make_config()))

    connection_module.initialize_pool()
    connection_module.initialize_pool()

    assert len(FakePool.instances) == 1
    assert FakePool.instances[0].open_calls == [(True, 30.0)]


def test_get_db_connection_returns_connection_to_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakePool.instances.clear()
    connection_module.reset_pool()
    monkeypatch.setattr(connection_module, "ConnectionPool", FakePool)
    monkeypatch.setattr(connection_module, "get_settings", lambda: FakeSettings(make_config()))

    with connection_module.get_db_connection(operation="unit_test") as conn:
        assert isinstance(conn, FakeConnection)

    assert FakePool.instances[0].returned_connection is conn


def test_execute_insert_commits_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConnection(cursor=FakeCursor(result={"id": 999}))
    returned: list[FakeConnection] = []

    monkeypatch.setattr(connection_module, "get_connection", lambda timeout=None: conn)
    monkeypatch.setattr(
        connection_module, "return_connection", lambda returned_conn: returned.append(returned_conn)
    )
    monkeypatch.setattr(connection_module, "get_settings", lambda: FakeSettings(make_config()))

    result = connection_module.execute_insert(
        "INSERT INTO tpi.test VALUES (%s) RETURNING id",
        params=(1,),
        return_id=True,
    )

    assert conn.commit_called is True
    assert returned == [conn]
    assert result == {"id": 999}


def test_get_db_connection_rolls_back_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = FakeConnection()
    returned: list[FakeConnection] = []

    monkeypatch.setattr(connection_module, "get_connection", lambda timeout=None: conn)
    monkeypatch.setattr(
        connection_module, "return_connection", lambda returned_conn: returned.append(returned_conn)
    )
    monkeypatch.setattr(connection_module, "get_settings", lambda: FakeSettings(make_config()))

    with pytest.raises(DatabaseAppError):
        with connection_module.get_db_connection(operation="unit_test_failure"):
            conn.info.transaction_status = psycopg.pq.TransactionStatus.INTRANS
            raise RuntimeError("boom")

    assert conn.rollback_called is True
    assert returned == [conn]
