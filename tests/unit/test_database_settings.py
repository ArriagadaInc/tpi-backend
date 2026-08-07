"""Unit tests for database settings resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config.settings import Settings

DATABASE_ENV_KEYS = [
    "APP_ENV",
    "DATABASE_URL",
    "DATABASE_HOST",
    "DATABASE_PORT",
    "DATABASE_NAME",
    "DATABASE_USER",
    "DATABASE_PASSWORD",
    "DATABASE_SCHEMA",
    "DATABASE_SSLMODE",
    "DATABASE_SSLROOTCERT",
    "DATABASE_CONNECT_TIMEOUT",
    "DATABASE_POOL_MIN_SIZE",
    "DATABASE_POOL_MAX_SIZE",
    "DATABASE_POOL_TIMEOUT",
]


def build_settings(monkeypatch: pytest.MonkeyPatch, **values: str) -> Settings:
    for key in DATABASE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    for key, value in values.items():
        monkeypatch.setenv(key, value)

    return Settings(_env_file=None)


def test_loads_database_configuration_from_discrete_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(
        monkeypatch,
        APP_ENV="testing",
        DATABASE_HOST="db.local",
        DATABASE_PORT="5433",
        DATABASE_NAME="tpi_test",
        DATABASE_USER="tpi_test_user",
        DATABASE_PASSWORD="secret-value",
        DATABASE_SSLMODE="disable",
        DATABASE_CONNECT_TIMEOUT="11",
        DATABASE_POOL_MIN_SIZE="2",
        DATABASE_POOL_MAX_SIZE="8",
        DATABASE_POOL_TIMEOUT="22",
    )

    config = settings.database_config

    assert config.source == "database_fields"
    assert config.host == "db.local"
    assert config.port == 5433
    assert config.database == "tpi_test"
    assert config.user == "tpi_test_user"
    assert config.password == "secret-value"
    assert config.connect_timeout == 11
    assert config.pool_min_size == 2
    assert config.pool_max_size == 8
    assert config.pool_timeout == 22


def test_local_defaults_apply_only_to_local_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(monkeypatch, APP_ENV="local")
    config = settings.database_config

    assert config.source == "local_defaults"
    assert config.host == "localhost"
    assert config.port == 5432
    assert config.database == "tpi_local"
    assert config.user == "tpi_app"
    assert config.password is None


def test_missing_required_database_fields_raise_in_non_local_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(
        monkeypatch,
        APP_ENV="testing",
        DATABASE_HOST="db.local",
    )

    with pytest.raises(ValueError, match="Missing required database settings"):
        _ = settings.database_config


def test_database_url_has_precedence_over_discrete_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(
        monkeypatch,
        APP_ENV="testing",
        DATABASE_URL=(
            "postgresql://url_user:url_password@url-host:6543/url_db"
            "?sslmode=disable&connect_timeout=9"
        ),
        DATABASE_HOST="ignored-host",
        DATABASE_PORT="1111",
        DATABASE_NAME="ignored_db",
        DATABASE_USER="ignored_user",
        DATABASE_PASSWORD="ignored_password",
        DATABASE_SSLMODE="require",
        DATABASE_POOL_MIN_SIZE="1",
        DATABASE_POOL_MAX_SIZE="3",
        DATABASE_POOL_TIMEOUT="18",
    )

    config = settings.database_config

    assert config.source == "database_url"
    assert config.host == "url-host"
    assert config.port == 6543
    assert config.database == "url_db"
    assert config.user == "url_user"
    assert config.password == "url_password"
    assert config.sslmode == "disable"
    assert config.connect_timeout == 9


def test_safe_summary_and_string_representation_redact_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(
        monkeypatch,
        APP_ENV="testing",
        DATABASE_HOST="db.local",
        DATABASE_PORT="5432",
        DATABASE_NAME="tpi_test",
        DATABASE_USER="tpi_test_user",
        DATABASE_PASSWORD="very-secret-password",
        DATABASE_SSLMODE="disable",
    )

    summary = settings.database_config.safe_summary()
    rendered_settings = str(settings)

    assert "very-secret-password" not in summary
    assert "very-secret-password" not in rendered_settings
    assert "db.local:5432/tpi_test" in summary


def test_connection_parameters_include_ssl_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temp_dir = Path.cwd() / ".tmp-tests"
    temp_dir.mkdir(exist_ok=True)
    certificate_path = temp_dir / "rds-ca.pem"
    certificate_path.write_text("fake-cert", encoding="utf-8")

    settings = build_settings(
        monkeypatch,
        APP_ENV="production",
        DATABASE_HOST="prod-host",
        DATABASE_PORT="5432",
        DATABASE_NAME="tpi",
        DATABASE_USER="tpi_app",
        DATABASE_PASSWORD="prod-secret",
        DATABASE_SSLMODE="verify-full",
        DATABASE_SSLROOTCERT=str(certificate_path),
    )

    params = settings.database_config.connection_parameters()

    assert params["sslmode"] == "verify-full"
    assert params["sslrootcert"] == str(certificate_path)
    assert params["connect_timeout"] == 10


def test_aws_dev_requires_secure_sslmode(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = build_settings(
        monkeypatch,
        APP_ENV="aws-dev",
        DATABASE_HOST="aws-host",
        DATABASE_PORT="5432",
        DATABASE_NAME="tpi",
        DATABASE_USER="tpi_app",
        DATABASE_PASSWORD="aws-secret",
    )

    with pytest.raises(ValueError, match="DATABASE_SSLMODE must enforce SSL"):
        _ = settings.database_config


def test_production_requires_verify_full_and_ca_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(
        monkeypatch,
        APP_ENV="production",
        DATABASE_HOST="prod-host",
        DATABASE_PORT="5432",
        DATABASE_NAME="tpi",
        DATABASE_USER="tpi_app",
        DATABASE_PASSWORD="prod-secret",
        DATABASE_SSLMODE="require",
    )

    with pytest.raises(ValueError, match="Production requires DATABASE_SSLMODE=verify-full"):
        _ = settings.database_config
