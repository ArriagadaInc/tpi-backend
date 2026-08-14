"""Unit tests for the AWS DEV-only test lead cleanup guard."""

from __future__ import annotations

import logging
from uuid import UUID

import pytest

from app.config import Settings
from app.database.errors import DevLeadCleanupBlockedError
from app.services.solicitud_service import SolicitudService

LEAD_ID = UUID("11111111-1111-1111-1111-111111111111")


class FakeRepository:
    """Small repository double that records calls without a database."""

    def __init__(
        self, *, exists: bool = True, delete_result: bool = True, error: Exception | None = None
    ):
        self.exists = exists
        self.delete_result = delete_result
        self.error = error
        self.delete_calls: list[UUID] = []

    def test_lead_exists(self, id_lead: UUID) -> bool:
        return self.exists

    def delete_test_lead(self, id_lead: UUID) -> bool:
        self.delete_calls.append(id_lead)
        if self.error:
            raise self.error
        return self.delete_result


def build_settings(app_env: str, enabled: bool) -> Settings:
    return Settings(
        _env_file=None,
        APP_ENV=app_env,
        DEV_DELETE_ENABLED=str(enabled).lower(),
    )


@pytest.mark.parametrize(
    ("app_env", "enabled", "expected"),
    [
        ("aws-dev", True, True),
        ("aws-dev", False, False),
        ("production", True, False),
        ("production", False, False),
        ("local", True, False),
    ],
)
def test_cleanup_guard_requires_aws_dev_and_enabled_flag(
    app_env: str,
    enabled: bool,
    expected: bool,
) -> None:
    service = SolicitudService(FakeRepository(), build_settings(app_env, enabled))  # type: ignore[arg-type]

    assert service.is_test_lead_cleanup_enabled() is expected


def test_delete_test_lead_succeeds_only_when_guard_is_enabled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = FakeRepository()
    service = SolicitudService(repository, build_settings("aws-dev", True))  # type: ignore[arg-type]

    with caplog.at_level(logging.INFO, logger="app.services.solicitud_service"):
        result = service.delete_test_lead(LEAD_ID)

    assert result.status == "deleted"
    assert result.deleted
    assert result.message == "Lead de prueba eliminado correctamente."
    assert repository.delete_calls == [LEAD_ID]
    assert "event=test_lead_deleted" in caplog.text
    assert str(LEAD_ID) in caplog.text


def test_delete_test_lead_is_denied_before_repository_access_outside_aws_dev() -> None:
    repository = FakeRepository()
    service = SolicitudService(repository, build_settings("production", True))  # type: ignore[arg-type]

    result = service.delete_test_lead(LEAD_ID)

    assert result.status == "denied"
    assert not repository.delete_calls


def test_delete_test_lead_rejects_invalid_uuid() -> None:
    repository = FakeRepository()
    service = SolicitudService(repository, build_settings("aws-dev", True))  # type: ignore[arg-type]

    result = service.delete_test_lead("not-a-uuid")

    assert result.status == "invalid"
    assert "identificador" in result.message
    assert not repository.delete_calls


def test_delete_test_lead_is_idempotent_when_missing() -> None:
    repository = FakeRepository(exists=False)
    service = SolicitudService(repository, build_settings("aws-dev", True))  # type: ignore[arg-type]

    result = service.delete_test_lead(LEAD_ID)

    assert result.status == "not_found"
    assert not repository.delete_calls


def test_delete_test_lead_reports_operational_dependencies_without_internal_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = FakeRepository(
        error=DevLeadCleanupBlockedError("internal database detail", operation="delete_test_lead")
    )
    service = SolicitudService(repository, build_settings("aws-dev", True))  # type: ignore[arg-type]

    with caplog.at_level(logging.WARNING, logger="app.services.solicitud_service"):
        result = service.delete_test_lead(LEAD_ID)

    assert result.status == "blocked"
    assert "internal database detail" not in result.message
    assert "event=test_lead_delete_failed" in caplog.text
    assert "internal database detail" not in caplog.text


def test_delete_test_lead_hides_repository_error_and_sensitive_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = FakeRepository(error=RuntimeError("password=secret RUT=12345678-5"))
    service = SolicitudService(repository, build_settings("aws-dev", True))  # type: ignore[arg-type]

    with caplog.at_level(logging.ERROR, logger="app.services.solicitud_service"):
        result = service.delete_test_lead(LEAD_ID)

    assert result.status == "failed"
    assert "secret" not in result.message
    assert "12345678-5" not in result.message
    assert "secret" not in caplog.text
    assert "12345678-5" not in caplog.text
