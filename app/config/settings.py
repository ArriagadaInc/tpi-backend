"""
Centralized application settings.

This module keeps a single typed source of truth for database configuration
across local development, testing, AWS development, and future production.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs, unquote, urlparse

from psycopg.conninfo import make_conninfo
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnvironment = Literal["local", "testing", "aws-dev", "production"]
DatabaseSource = Literal["database_url", "database_fields", "local_defaults"]

_DEFAULT_LOCAL_HOST = "localhost"
_DEFAULT_LOCAL_PORT = 5432
_DEFAULT_LOCAL_DATABASE = "tpi_local"
_DEFAULT_LOCAL_USER = "tpi_app"
_DEFAULT_DATABASE_SCHEMA = "tpi"
_DEFAULT_CONNECT_TIMEOUT = 10
_DEFAULT_POOL_MIN_SIZE = 1
_DEFAULT_POOL_MAX_SIZE = 5
_DEFAULT_POOL_TIMEOUT = 30
_DEFAULT_LOCAL_SSLMODE = "disable"
_ALLOWED_SSL_MODES = {
    "disable",
    "allow",
    "prefer",
    "require",
    "verify-ca",
    "verify-full",
}
_SECURE_AWS_SSL_MODES = {"require", "verify-ca", "verify-full"}
_APP_ENV_ALIASES = {
    "development": "local",
    "dev": "local",
    "staging": "aws-dev",
    "aws_dev": "aws-dev",
}


@dataclass(frozen=True, slots=True)
class DatabaseConnectionConfig:
    """Resolved database connection settings."""

    app_env: AppEnvironment
    source: DatabaseSource
    host: str
    port: int
    database: str
    user: str
    password: str | None
    schema: str
    sslmode: str
    sslrootcert: str | None
    connect_timeout: int
    pool_min_size: int
    pool_max_size: int
    pool_timeout: int
    application_name: str

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"

    @property
    def is_testing(self) -> bool:
        return self.app_env == "testing"

    @property
    def is_aws(self) -> bool:
        return self.app_env in {"aws-dev", "production"}

    def connection_parameters(self) -> dict[str, Any]:
        """Build psycopg connection parameters without exposing secrets."""
        params: dict[str, Any] = {
            "host": self.host,
            "port": self.port,
            "dbname": self.database,
            "user": self.user,
            "sslmode": self.sslmode,
            "connect_timeout": self.connect_timeout,
            "application_name": self.application_name,
        }

        if self.password:
            params["password"] = self.password

        if self.sslrootcert:
            params["sslrootcert"] = self.sslrootcert

        return params

    def conninfo(self) -> str:
        """Build a psycopg-native conninfo string."""
        return make_conninfo(**self.connection_parameters())

    def pool_signature(self) -> tuple[str, ...]:
        """Return an in-memory signature to detect pool config changes."""
        return (
            self.app_env,
            self.source,
            self.host,
            str(self.port),
            self.database,
            self.user,
            self.password or "",
            self.schema,
            self.sslmode,
            self.sslrootcert or "",
            str(self.connect_timeout),
            str(self.pool_min_size),
            str(self.pool_max_size),
            str(self.pool_timeout),
        )

    def safe_summary(self) -> str:
        """Human-readable summary without secrets."""
        return (
            f"DatabaseConnectionConfig(env={self.app_env}, source={self.source}, "
            f"target={self.host}:{self.port}/{self.database}, user={self.user}, "
            f"schema={self.schema}, sslmode={self.sslmode}, "
            f"pool={self.pool_min_size}-{self.pool_max_size}, "
            f"connect_timeout={self.connect_timeout}s, pool_timeout={self.pool_timeout}s)"
        )

    def __str__(self) -> str:
        return self.safe_summary()


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    app_env: str = Field(default="local", alias="APP_ENV")
    app_name: str = Field(default="Tu Pension Inteligente Back-office", alias="APP_NAME")
    app_debug: bool = Field(default=False, alias="APP_DEBUG")
    dev_delete_enabled: bool = Field(default=False, alias="DEV_DELETE_ENABLED")
    lead_notifications_enabled: bool = Field(default=False, alias="LEAD_NOTIFICATIONS_ENABLED")
    lead_notification_topic_arn: str | None = Field(
        default=None, alias="LEAD_NOTIFICATION_TOPIC_ARN"
    )
    auth_enabled: bool = Field(default=False, alias="AUTH_ENABLED")
    auth_mode: str = Field(default="simple-dev", alias="AUTH_MODE")
    auth_users_json: SecretStr | None = Field(default=None, alias="AUTH_USERS_JSON")
    web_session_secret: SecretStr | None = Field(default=None, alias="WEB_SESSION_SECRET")
    web_session_max_age_seconds: int = Field(default=28800, alias="WEB_SESSION_MAX_AGE_SECONDS")
    web_mask_pii: bool = Field(default=True, alias="WEB_MASK_PII")
    public_site_url: str | None = Field(default=None, alias="TPI_PUBLIC_SITE_URL")
    api_idempotency_hmac_secret: SecretStr | None = Field(
        default=None, alias="API_IDEMPOTENCY_HMAC_SECRET"
    )
    api_max_request_bytes: int = Field(default=16384, alias="API_MAX_REQUEST_BYTES")
    api_rate_limit_requests: int = Field(default=5, alias="API_RATE_LIMIT_REQUESTS")
    api_rate_limit_window_seconds: int = Field(default=600, alias="API_RATE_LIMIT_WINDOW_SECONDS")
    api_trusted_proxy_cidrs: str = Field(default="", alias="API_TRUSTED_PROXY_CIDRS")

    database_url: SecretStr | None = Field(default=None, alias="DATABASE_URL")
    database_host: str | None = Field(default=None, alias="DATABASE_HOST")
    database_port: int | None = Field(default=None, alias="DATABASE_PORT")
    database_name: str | None = Field(default=None, alias="DATABASE_NAME")
    database_user: str | None = Field(default=None, alias="DATABASE_USER")
    database_password: SecretStr | None = Field(default=None, alias="DATABASE_PASSWORD")
    database_schema: str = Field(default=_DEFAULT_DATABASE_SCHEMA, alias="DATABASE_SCHEMA")
    database_sslmode: str | None = Field(default=None, alias="DATABASE_SSLMODE")
    database_sslrootcert: str | None = Field(default=None, alias="DATABASE_SSLROOTCERT")
    database_connect_timeout: int = Field(
        default=_DEFAULT_CONNECT_TIMEOUT,
        alias="DATABASE_CONNECT_TIMEOUT",
    )
    database_pool_min_size: int = Field(
        default=_DEFAULT_POOL_MIN_SIZE,
        alias="DATABASE_POOL_MIN_SIZE",
    )
    database_pool_max_size: int = Field(
        default=_DEFAULT_POOL_MAX_SIZE,
        alias="DATABASE_POOL_MAX_SIZE",
    )
    database_pool_timeout: int = Field(
        default=_DEFAULT_POOL_TIMEOUT,
        alias="DATABASE_POOL_TIMEOUT",
    )

    privacy_policy_version: str = Field(default="demo-2026-01", alias="PRIVACY_POLICY_VERSION")
    terms_version: str = Field(default="demo-2026-01", alias="TERMS_VERSION")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: str = Field(default="logs/backoffice.log", alias="LOG_FILE")
    allow_demo_mode: bool = Field(default=False, alias="ALLOW_DEMO_MODE")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("app_env", mode="before")
    @classmethod
    def validate_env(cls, value: str | None) -> str:
        raw = (value or "local").strip().lower()
        normalized = _APP_ENV_ALIASES.get(raw, raw)
        valid_envs = {"local", "testing", "aws-dev", "production"}

        if normalized not in valid_envs:
            raise ValueError(f"APP_ENV must be one of: {sorted(valid_envs)}")

        return normalized

    @field_validator("database_schema", mode="before")
    @classmethod
    def validate_schema(cls, value: str | None) -> str:
        schema = (value or _DEFAULT_DATABASE_SCHEMA).strip()
        if not schema:
            raise ValueError("DATABASE_SCHEMA cannot be empty")
        return schema

    @field_validator("database_sslmode", mode="before")
    @classmethod
    def validate_sslmode(cls, value: str | None) -> str | None:
        if value is None:
            return None

        sslmode = value.strip().lower()
        if not sslmode:
            return None

        if sslmode not in _ALLOWED_SSL_MODES:
            raise ValueError(f"DATABASE_SSLMODE must be one of: {sorted(_ALLOWED_SSL_MODES)}")

        return sslmode

    @field_validator(
        "database_connect_timeout",
        "database_pool_min_size",
        "database_pool_max_size",
        "database_pool_timeout",
    )
    @classmethod
    def validate_positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Database timeouts and pool sizes must be positive integers")
        return value

    @field_validator(
        "api_max_request_bytes",
        "api_rate_limit_requests",
        "api_rate_limit_window_seconds",
        "web_session_max_age_seconds",
    )
    @classmethod
    def validate_positive_api_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("API limits must be positive integers")
        return value

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = value.upper()
        if normalized not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of: {sorted(valid_levels)}")
        return normalized

    @property
    def normalized_app_env(self) -> AppEnvironment:
        return self.app_env  # type: ignore[return-value]

    @property
    def is_local(self) -> bool:
        return self.normalized_app_env == "local"

    @property
    def is_testing(self) -> bool:
        return self.normalized_app_env == "testing"

    @property
    def is_production(self) -> bool:
        return self.normalized_app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.is_local

    @property
    def is_aws(self) -> bool:
        return self.normalized_app_env in {"aws-dev", "production"}

    @property
    def should_mask_web_pii(self) -> bool:
        return self.is_production or self.web_mask_pii

    @property
    def is_test_lead_cleanup_enabled(self) -> bool:
        """Allow test-data cleanup only in the explicitly enabled AWS DEV environment."""
        return self.normalized_app_env == "aws-dev" and self.dev_delete_enabled

    @property
    def authentication_required(self) -> bool:
        """Require auth in deployed environments; local/test remain explicitly controlled."""
        return (
            self.normalized_app_env in {"aws-dev", "production"}
            or self.auth_enabled
            or self.auth_mode != "simple-dev"
        )

    def validate_auth_configuration(self) -> None:
        """Validate auth safely before any protected page accesses application data."""
        if not self.authentication_required:
            return

        if self.normalized_app_env == "production":
            raise ValueError("Production requires an approved OIDC authentication provider")

        if not self.auth_enabled:
            raise ValueError("AUTH_ENABLED must be true in aws-dev")

        if self.auth_mode != "simple-dev":
            raise ValueError("AUTH_MODE is not supported")

        if self.auth_users_json is None or not self.auth_users_json.get_secret_value().strip():
            raise ValueError("AUTH_USERS_JSON must be configured when authentication is enabled")

    def validate_public_api_configuration(self) -> None:
        """Fail closed when the public API lacks its dedicated HMAC secret."""
        if (
            self.api_idempotency_hmac_secret is None
            or not self.api_idempotency_hmac_secret.get_secret_value().strip()
        ):
            raise ValueError("API_IDEMPOTENCY_HMAC_SECRET must be configured for the public API")

    @property
    def database_config(self) -> DatabaseConnectionConfig:
        """Resolve and validate database configuration on demand."""
        if self.database_pool_min_size > self.database_pool_max_size:
            raise ValueError("DATABASE_POOL_MIN_SIZE cannot be greater than DATABASE_POOL_MAX_SIZE")

        if self.database_url:
            return self._resolve_from_database_url(self.database_url.get_secret_value())

        return self._resolve_from_database_fields()

    def get_database_url(self) -> str:
        """Backwards-compatible helper returning psycopg conninfo."""
        return self.database_config.conninfo()

    def _resolve_from_database_url(self, database_url: str) -> DatabaseConnectionConfig:
        parsed = _parse_database_url(database_url)
        sslmode = (
            parsed["sslmode"] or self.database_sslmode or _default_sslmode(self.normalized_app_env)
        )
        sslrootcert = parsed["sslrootcert"] or self.database_sslrootcert
        connect_timeout = parsed["connect_timeout"] or self.database_connect_timeout
        password = parsed["password"]

        config = DatabaseConnectionConfig(
            app_env=self.normalized_app_env,
            source="database_url",
            host=parsed["host"],
            port=parsed["port"],
            database=parsed["database"],
            user=parsed["user"],
            password=password,
            schema=self.database_schema,
            sslmode=sslmode,
            sslrootcert=sslrootcert,
            connect_timeout=connect_timeout,
            pool_min_size=self.database_pool_min_size,
            pool_max_size=self.database_pool_max_size,
            pool_timeout=self.database_pool_timeout,
            application_name=_build_application_name(self.app_name, self.normalized_app_env),
        )
        self._validate_database_config(config)
        return config

    def _resolve_from_database_fields(self) -> DatabaseConnectionConfig:
        using_local_defaults = self.is_local and not any(
            [
                self.database_host,
                self.database_port,
                self.database_name,
                self.database_user,
                self.database_password,
            ]
        )

        host: str | None
        port: int | None
        database: str | None
        user: str | None
        password: str | None

        if using_local_defaults:
            host = _DEFAULT_LOCAL_HOST
            port = _DEFAULT_LOCAL_PORT
            database = _DEFAULT_LOCAL_DATABASE
            user = _DEFAULT_LOCAL_USER
            password = None
            source: DatabaseSource = "local_defaults"
        else:
            host = self.database_host or (_DEFAULT_LOCAL_HOST if self.is_local else None)
            port = self.database_port or (_DEFAULT_LOCAL_PORT if self.is_local else None)
            database = self.database_name or (_DEFAULT_LOCAL_DATABASE if self.is_local else None)
            user = self.database_user or (_DEFAULT_LOCAL_USER if self.is_local else None)
            password = (
                self.database_password.get_secret_value()
                if self.database_password is not None
                else None
            )
            source = "database_fields"

        missing_fields = [
            name
            for name, value in (
                ("DATABASE_HOST", host),
                ("DATABASE_PORT", port),
                ("DATABASE_NAME", database),
                ("DATABASE_USER", user),
            )
            if value in (None, "")
        ]

        if missing_fields:
            raise ValueError("Missing required database settings: " + ", ".join(missing_fields))

        if host is None or port is None or database is None or user is None:
            raise RuntimeError("Validated database settings are missing required values")

        sslmode = self.database_sslmode or _default_sslmode(self.normalized_app_env)
        config = DatabaseConnectionConfig(
            app_env=self.normalized_app_env,
            source=source,
            host=str(host),
            port=int(port),
            database=str(database),
            user=str(user),
            password=password,
            schema=self.database_schema,
            sslmode=sslmode,
            sslrootcert=self.database_sslrootcert,
            connect_timeout=self.database_connect_timeout,
            pool_min_size=self.database_pool_min_size,
            pool_max_size=self.database_pool_max_size,
            pool_timeout=self.database_pool_timeout,
            application_name=_build_application_name(self.app_name, self.normalized_app_env),
        )
        self._validate_database_config(config)
        return config

    def _validate_database_config(self, config: DatabaseConnectionConfig) -> None:
        if config.port <= 0:
            raise ValueError("DATABASE_PORT must be a positive integer")

        if config.connect_timeout <= 0:
            raise ValueError("DATABASE_CONNECT_TIMEOUT must be a positive integer")

        if config.pool_min_size > config.pool_max_size:
            raise ValueError("DATABASE_POOL_MIN_SIZE cannot exceed DATABASE_POOL_MAX_SIZE")

        if config.is_aws:
            if config.sslmode not in _SECURE_AWS_SSL_MODES:
                raise ValueError(
                    "DATABASE_SSLMODE must enforce SSL in aws-dev/production "
                    "(require, verify-ca, or verify-full)"
                )

            if not config.password:
                raise ValueError("DATABASE_PASSWORD must be set for aws-dev/production connections")

        if config.app_env == "production":
            if config.sslmode != "verify-full":
                raise ValueError("Production requires DATABASE_SSLMODE=verify-full")

            if not config.sslrootcert:
                raise ValueError(
                    "Production requires DATABASE_SSLROOTCERT with the RDS CA bundle path"
                )

        if config.sslrootcert:
            cert_path = Path(config.sslrootcert)
            if not cert_path.exists():
                raise ValueError(f"DATABASE_SSLROOTCERT does not exist: {config.sslrootcert}")

    def __str__(self) -> str:
        try:
            return (
                f"Settings(env={self.normalized_app_env}, "
                f"db={self.database_config.safe_summary()}, debug={self.app_debug})"
            )
        except ValueError:
            return (
                f"Settings(env={self.normalized_app_env}, "
                f"db=<unresolved>, debug={self.app_debug})"
            )


def _default_sslmode(app_env: AppEnvironment) -> str:
    return _DEFAULT_LOCAL_SSLMODE


def _build_application_name(app_name: str, app_env: AppEnvironment) -> str:
    safe_name = app_name.lower().replace(" ", "-")
    return f"{safe_name[:40]}-{app_env}"


def _parse_database_url(database_url: str) -> dict[str, Any]:
    normalized_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    parsed = urlparse(normalized_url)

    if parsed.scheme.lower() not in {"postgresql", "postgres"}:
        raise ValueError("DATABASE_URL must use a PostgreSQL scheme")

    if not parsed.hostname:
        raise ValueError("DATABASE_URL must include a host")

    database_name = parsed.path.lstrip("/")
    if not database_name:
        raise ValueError("DATABASE_URL must include a database name")

    if not parsed.username:
        raise ValueError("DATABASE_URL must include a user")

    query_params = parse_qs(parsed.query)
    connect_timeout = query_params.get("connect_timeout", [None])[-1]

    return {
        "host": parsed.hostname,
        "port": parsed.port or _DEFAULT_LOCAL_PORT,
        "database": database_name,
        "user": unquote(parsed.username),
        "password": unquote(parsed.password) if parsed.password else None,
        "sslmode": _normalize_optional_sslmode(query_params.get("sslmode", [None])[-1]),
        "sslrootcert": query_params.get("sslrootcert", [None])[-1],
        "connect_timeout": int(connect_timeout) if connect_timeout else None,
    }


def _normalize_optional_sslmode(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip().lower()
    if not normalized:
        return None

    if normalized not in _ALLOWED_SSL_MODES:
        raise ValueError(f"Invalid sslmode in DATABASE_URL: {normalized}")

    return normalized


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings for the current process."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return Settings(_env_file=".env", _env_file_encoding="utf-8")  # type: ignore[call-arg]

    env_files: tuple[str, ...] = (".env",)
    local_env = Path(".env.local")
    if local_env.exists():
        env_files = (".env", ".env.local")
    return Settings(_env_file=env_files, _env_file_encoding="utf-8")  # type: ignore[call-arg]


def clear_settings_cache() -> None:
    """Clear cached settings, mainly for tests."""
    get_settings.cache_clear()


class SettingsProxy:
    """Lazy proxy preserving the historic `settings` import style."""

    def __getattr__(self, name: str) -> Any:
        return getattr(get_settings(), name)

    def __str__(self) -> str:
        return str(get_settings())


settings = SettingsProxy()
