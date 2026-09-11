"""Regression tests for the one-shot H3.3 phase-1 domain-baseline promotion."""

from __future__ import annotations

import base64
from typing import Any

import pytest

from deployment.aws.promote_domain_baseline import (
    BASELINE_BUCKET,
    BASELINE_KEY,
    BASELINE_SHA256,
    BASELINE_VERSION_ID,
    EXPECTED_METADATA,
    SOURCE_DEV_ENVIRONMENT,
    SOURCE_VERSION,
    TARGET_DEV_ENVIRONMENT,
    TARGET_VERSION,
    BaselinePromoter,
)

BASELINE_CHECKSUM_B64 = base64.b64encode(bytes.fromhex(BASELINE_SHA256)).decode("ascii")


def source_version() -> dict[str, object]:
    return {
        "VersionLabel": SOURCE_VERSION,
        "Status": "PROCESSED",
        "SourceBundle": {"S3Bucket": "legacy", "S3Key": "legacy.zip"},
    }


def target_version(**overrides: Any) -> dict[str, object]:
    value: dict[str, object] = {
        "VersionLabel": TARGET_VERSION,
        "Status": "UNPROCESSED",
        "SourceBundle": {"S3Bucket": BASELINE_BUCKET, "S3Key": BASELINE_KEY},
    }
    value.update(overrides)
    return value


class FakeAws:
    def __init__(self, *, environment_version: str, target: dict[str, object] | None) -> None:
        self.environment_version = environment_version
        self.target = target
        self.healthy = True
        self.degrade_after_update = False
        self.fail_update = False
        self.head_version_id = BASELINE_VERSION_ID
        self.head_checksum = BASELINE_CHECKSUM_B64
        self.head_metadata = dict(EXPECTED_METADATA)
        self.calls: list[tuple[str, ...]] = []

    def json(self, *arguments: str) -> object:
        self.calls.append(arguments)
        command = " ".join(arguments)
        if command.startswith("sts get-caller-identity"):
            return {"Account": "821656895812"}
        if "head-object" in command:
            return {
                "VersionId": self.head_version_id,
                "ChecksumSHA256": self.head_checksum,
                "Metadata": dict(self.head_metadata),
            }
        if "describe-environments" in command:
            return {
                "Environments": [
                    {
                        "ApplicationName": "tpi-backoffice",
                        "EnvironmentName": "tpi-backoffice-dev-green",
                        "VersionLabel": self.environment_version,
                        "Status": "Ready",
                        "Health": "Green" if self.healthy else "Degraded",
                        "HealthStatus": "Ok" if self.healthy else "Error",
                    }
                ]
            }
        if "describe-application-versions" in command:
            label = arguments[arguments.index("--version-labels") + 1]
            if label == SOURCE_VERSION:
                return {"ApplicationVersions": [source_version()]}
            return {"ApplicationVersions": [] if self.target is None else [self.target]}
        if "create-application-version" in command:
            self.target = target_version()
            return {"ApplicationVersion": self.target}
        if "update-environment" in command:
            if self.fail_update:
                raise RuntimeError("original update failure")
            version = arguments[arguments.index("--version-label") + 1]
            self.environment_version = version
            if version == TARGET_VERSION and self.degrade_after_update:
                self.healthy = False
            else:
                self.healthy = True
            return {}
        if "describe-events" in command:
            return {"Events": [{"Message": "diagnostic event"}]}
        raise AssertionError(f"Unexpected AWS call: {command}")


def test_promotes_baseline_once_with_four_tpi_variables() -> None:
    aws = FakeAws(environment_version=SOURCE_VERSION, target=None)

    BaselinePromoter(aws).run()

    creates = [call for call in aws.calls if "create-application-version" in " ".join(call)]
    updates = [call for call in aws.calls if "update-environment" in " ".join(call)]
    assert len(creates) == 1
    assert len(updates) == 1

    create = creates[0]
    source_bundle = create[create.index("--source-bundle") + 1]
    assert source_bundle == f"S3Bucket={BASELINE_BUCKET},S3Key={BASELINE_KEY}"

    update = updates[0]
    assert update[update.index("--version-label") + 1] == TARGET_VERSION
    assert "--options-to-remove" not in update
    settings = update[update.index("--option-settings") + 1 :]
    assert set(settings) == {
        f"Namespace=aws:elasticbeanstalk:application:environment,OptionName={name},Value={value}"
        for name, value in TARGET_DEV_ENVIRONMENT.items()
    }


def test_wrong_source_version_fails_closed_before_any_write() -> None:
    aws = FakeAws(environment_version="h2-5d-ecr-47fa0c9", target=None)

    with pytest.raises(RuntimeError, match="not healthy on required version"):
        BaselinePromoter(aws).run()

    commands = [" ".join(call) for call in aws.calls]
    assert not any("create-application-version" in call for call in commands)
    assert not any("update-environment" in call for call in commands)


def test_wrong_s3_version_id_fails_closed() -> None:
    aws = FakeAws(environment_version=SOURCE_VERSION, target=None)
    aws.head_version_id = "WRONG.VersionId"

    with pytest.raises(RuntimeError, match="VersionId"):
        BaselinePromoter(aws).run()

    commands = [" ".join(call) for call in aws.calls]
    assert not any("create-application-version" in call for call in commands)
    assert not any("update-environment" in call for call in commands)


def test_wrong_s3_checksum_fails_closed() -> None:
    aws = FakeAws(environment_version=SOURCE_VERSION, target=None)
    aws.head_checksum = base64.b64encode(b"\x00" * 32).decode("ascii")

    with pytest.raises(RuntimeError, match="checksum"):
        BaselinePromoter(aws).run()

    commands = [" ".join(call) for call in aws.calls]
    assert not any("create-application-version" in call for call in commands)
    assert not any("update-environment" in call for call in commands)


def test_wrong_s3_metadata_fails_closed() -> None:
    aws = FakeAws(environment_version=SOURCE_VERSION, target=None)
    aws.head_metadata["artifact-type"] = "wrong-artifact"

    with pytest.raises(RuntimeError, match="metadata"):
        BaselinePromoter(aws).run()

    commands = [" ".join(call) for call in aws.calls]
    assert not any("create-application-version" in call for call in commands)
    assert not any("update-environment" in call for call in commands)


def test_existing_target_with_wrong_source_bundle_fails_closed() -> None:
    bad = target_version(SourceBundle={"S3Bucket": "wrong", "S3Key": "wrong.zip"})
    aws = FakeAws(environment_version=SOURCE_VERSION, target=bad)

    with pytest.raises(RuntimeError, match="SourceBundle"):
        BaselinePromoter(aws).run()

    commands = [" ".join(call) for call in aws.calls]
    assert not any("create-application-version" in call for call in commands)
    assert not any("update-environment" in call for call in commands)


def test_existing_correct_target_is_not_recreated() -> None:
    aws = FakeAws(environment_version=SOURCE_VERSION, target=target_version())

    BaselinePromoter(aws).run()

    creates = [call for call in aws.calls if "create-application-version" in " ".join(call)]
    updates = [call for call in aws.calls if "update-environment" in " ".join(call)]
    assert len(creates) == 0
    assert len(updates) == 1


def test_healthy_target_after_update_does_not_rollback() -> None:
    aws = FakeAws(environment_version=SOURCE_VERSION, target=None)

    BaselinePromoter(aws).run()

    updates = [call for call in aws.calls if "update-environment" in " ".join(call)]
    assert len(updates) == 1


def test_failure_before_update_does_not_rollback() -> None:
    aws = FakeAws(environment_version=SOURCE_VERSION, target=None)
    aws.head_version_id = "WRONG.VersionId"

    with pytest.raises(RuntimeError, match="VersionId"):
        BaselinePromoter(aws).run()

    updates = [call for call in aws.calls if "update-environment" in " ".join(call)]
    assert len(updates) == 0


def test_degraded_target_executes_exactly_one_legacy_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("time.sleep", lambda _: None)
    aws = FakeAws(environment_version=SOURCE_VERSION, target=None)
    aws.degrade_after_update = True

    with pytest.raises(TimeoutError, match="Timed out waiting for Ready/Green/Ok"):
        BaselinePromoter(aws).run()

    updates = [call for call in aws.calls if "update-environment" in " ".join(call)]
    assert len(updates) == 2
    promote, rollback = updates
    assert promote[promote.index("--version-label") + 1] == TARGET_VERSION
    assert "--options-to-remove" not in promote
    assert rollback[rollback.index("--version-label") + 1] == SOURCE_VERSION
    assert "--options-to-remove" in rollback
    assert rollback[rollback.index("--options-to-remove") + 1] == (
        "Namespace=aws:elasticbeanstalk:application:environment,"
        "OptionName=TPI_ROUTE53_HOSTED_ZONE_ID"
    )
    rollback_settings = rollback[
        rollback.index("--option-settings") + 1 : rollback.index("--options-to-remove")
    ]
    assert set(rollback_settings) == {
        f"Namespace=aws:elasticbeanstalk:application:environment,OptionName={name},Value={value}"
        for name, value in SOURCE_DEV_ENVIRONMENT.items()
    }
