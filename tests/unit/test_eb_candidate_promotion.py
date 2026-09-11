"""Regression tests for the H3.3 atomic Elastic Beanstalk cutover."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from deployment.aws.promote_eb_candidate import (
    SOURCE_DEV_ENVIRONMENT,
    TARGET_DEV_ENVIRONMENT,
    CandidatePromoter,
    PromotionContract,
)

SOURCE_VERSION = "h3-3-crm-web-28cf009-r1"
CANDIDATE_VERSION = "h3-3-crm-web-43101be-r1"
FROZEN_BUNDLE_SHA = "7a7c69d6bc005a82c331895da06fbdc26b1f1fa88ce3a23a4274629476d8cfbb"
FROZEN_S3_CHECKSUM = base64.b64encode(bytes.fromhex(FROZEN_BUNDLE_SHA)).decode()


class FakeAws:
    def __init__(self, *, candidate: dict[str, object] | None, environment_version: str) -> None:
        self.candidate = candidate
        self.environment_version = environment_version
        self.environment_contract = (
            dict(TARGET_DEV_ENVIRONMENT)
            if environment_version == CANDIDATE_VERSION
            else dict(SOURCE_DEV_ENVIRONMENT)
        )
        self.calls: list[tuple[str, ...]] = []
        self.fail_update = False
        self.corrupt_target_contract = False
        self.stored_checksum: str | None = FROZEN_S3_CHECKSUM
        self.head_checksum_override: str | None = None

    def json(self, *arguments: str) -> object:
        self.calls.append(arguments)
        command = " ".join(arguments)
        if command.startswith("sts get-caller-identity"):
            return {"Account": "821656895812"}
        if "s3api put-object" in command:
            self.stored_checksum = arguments[arguments.index("--checksum-sha256") + 1]
            return {"ChecksumSHA256": self.stored_checksum}
        if "s3api head-object" in command:
            return {"ChecksumSHA256": self.head_checksum_override or self.stored_checksum}
        if "describe-environments" in command:
            return {
                "Environments": [
                    {
                        "ApplicationName": "tpi-backoffice",
                        "EnvironmentName": "tpi-backoffice-dev-green",
                        "VersionLabel": self.environment_version,
                        "Status": "Ready",
                        "Health": "Green",
                        "HealthStatus": "Ok",
                    }
                ]
            }
        if "describe-configuration-settings" in command:
            return [
                {"Name": name, "Value": value} for name, value in self.environment_contract.items()
            ]
        if "describe-application-versions" in command:
            label = arguments[arguments.index("--version-labels") + 1]
            if label == SOURCE_VERSION:
                return {
                    "ApplicationVersions": [
                        {
                            "VersionLabel": SOURCE_VERSION,
                            "Status": "PROCESSED",
                            "SourceBundle": {"S3Bucket": "known", "S3Key": "known.zip"},
                        }
                    ]
                }
            return {"ApplicationVersions": [] if self.candidate is None else [self.candidate]}
        if "create-application-version" in command:
            source_bundle = arguments[arguments.index("--source-bundle") + 1]
            bucket, key = (part.split("=", 1)[1] for part in source_bundle.split(",", maxsplit=1))
            self.candidate = candidate_version(SourceBundle={"S3Bucket": bucket, "S3Key": key})
            return {"ApplicationVersion": self.candidate}
        if "update-environment" in command:
            if self.fail_update:
                raise RuntimeError("original update failure")
            version = arguments[arguments.index("--version-label") + 1]
            self.environment_version = version
            settings_start = arguments.index("--option-settings") + 1
            settings_end = (
                arguments.index("--options-to-remove")
                if "--options-to-remove" in arguments
                else len(arguments)
            )
            settings = arguments[settings_start:settings_end]
            self.environment_contract = {
                item.split(",OptionName=", 1)[1].split(",Value=", 1)[0]: item.rsplit(",Value=", 1)[
                    1
                ]
                for item in settings
            }
            if version == CANDIDATE_VERSION and self.corrupt_target_contract:
                self.environment_contract = dict(SOURCE_DEV_ENVIRONMENT)
            return {}
        if "describe-events" in command:
            return {"Events": [{"Message": "diagnostic event"}]}
        raise AssertionError(f"Unexpected AWS call: {command}")


def contract() -> PromotionContract:
    return PromotionContract(
        account_id="821656895812",
        region="us-east-2",
        application="tpi-backoffice",
        environment="tpi-backoffice-dev-green",
        current_version=SOURCE_VERSION,
        candidate_version=CANDIDATE_VERSION,
        approved_bundle_bucket="tpi-dev-release-artifacts-821656895812-us-east-2",
        approved_bundle_key=(
            "approved-releases/h3-3-crm-web-43101be-r1/"
            "7a7c69d6bc005a82c331895da06fbdc26b1f1fa88ce3a23a4274629476d8cfbb.zip"
        ),
        artifact_dir="artifact",
        bundle_name="tpi-dev-ecr-43101be.zip",
        runtime_sha="43101be7835088f93267bee85b0f11c8bc879867",
        bundle_sha256=FROZEN_BUNDLE_SHA,
    )


def materializable_contract(
    tmp_path: Path, content: bytes = b"verified bundle"
) -> PromotionContract:
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    (artifact_dir / "tpi-dev-ecr-43101be.zip").write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    return replace(
        contract(),
        artifact_dir=str(artifact_dir),
        bundle_sha256=digest,
        approved_bundle_key=f"approved-releases/h3-3-crm-web-43101be-r1/{digest}.zip",
    )


def candidate_version(**overrides: Any) -> dict[str, object]:
    value: dict[str, object] = {
        "VersionLabel": CANDIDATE_VERSION,
        "Status": "UNPROCESSED",
        "SourceBundle": {
            "S3Bucket": "tpi-dev-release-artifacts-821656895812-us-east-2",
            "S3Key": (
                "approved-releases/h3-3-crm-web-43101be-r1/"
                "7a7c69d6bc005a82c331895da06fbdc26b1f1fa88ce3a23a4274629476d8cfbb.zip"
            ),
        },
    }
    value.update(overrides)
    return value


def test_candidate_is_created_from_verified_bundle_before_atomic_update(tmp_path: Path) -> None:
    aws = FakeAws(candidate=None, environment_version=SOURCE_VERSION)
    promotion_contract = materializable_contract(tmp_path)

    CandidatePromoter(aws, promotion_contract).run()

    commands = list(map(" ".join, aws.calls))
    assert commands.index(
        next(call for call in commands if "s3api put-object" in call)
    ) < commands.index(next(call for call in commands if "create-application-version" in call))
    updates = [call for call in aws.calls if "update-environment" in " ".join(call)]
    assert len(updates) == 1
    assert updates[0][updates[0].index("--version-label") + 1] == CANDIDATE_VERSION
    assert "--options-to-remove" not in updates[0]
    assert set(updates[0][updates[0].index("--option-settings") + 1 :]) == {
        f"Namespace=aws:elasticbeanstalk:application:environment,OptionName={name},Value={value}"
        for name, value in TARGET_DEV_ENVIRONMENT.items()
    }
    assert aws.environment_contract == TARGET_DEV_ENVIRONMENT


def test_source_contract_mismatch_aborts_before_candidate_or_environment_write(
    tmp_path: Path,
) -> None:
    aws = FakeAws(candidate=None, environment_version=SOURCE_VERSION)
    aws.environment_contract["TPI_PUBLIC_SITE_URL"] = "https://dev.example.invalid/"

    with pytest.raises(RuntimeError, match="source domain contract mismatch"):
        CandidatePromoter(aws, materializable_contract(tmp_path)).run()

    commands = [" ".join(call) for call in aws.calls]
    assert not any("s3api put-object" in call for call in commands)
    assert not any("update-environment" in call for call in commands)


def test_invalid_bundle_or_existing_candidate_source_aborts_before_update(tmp_path: Path) -> None:
    bad_contract = replace(
        materializable_contract(tmp_path, b"incorrect bytes"), bundle_sha256=FROZEN_BUNDLE_SHA
    )
    aws = FakeAws(candidate=None, environment_version=SOURCE_VERSION)

    with pytest.raises(RuntimeError, match="bundle SHA256 mismatch"):
        CandidatePromoter(aws, bad_contract).run()
    assert not any("update-environment" in " ".join(call) for call in aws.calls)

    bad_source = candidate_version(SourceBundle={"S3Bucket": "unexpected", "S3Key": "other.zip"})
    aws = FakeAws(candidate=bad_source, environment_version=SOURCE_VERSION)
    with pytest.raises(RuntimeError, match="SourceBundle"):
        CandidatePromoter(aws, contract()).run()
    assert not any("update-environment" in " ".join(call) for call in aws.calls)


def test_candidate_uses_only_the_approved_immutable_source() -> None:
    aws = FakeAws(candidate=candidate_version(), environment_version=SOURCE_VERSION)

    CandidatePromoter(aws, contract()).run()

    assert not any("s3api put-object" in " ".join(call) for call in aws.calls)


def test_healthy_target_is_postflight_only() -> None:
    aws = FakeAws(candidate=candidate_version(), environment_version=CANDIDATE_VERSION)

    CandidatePromoter(aws, contract()).run()

    assert not any("update-environment" in " ".join(call) for call in aws.calls)


def test_failed_request_does_not_trigger_rollback() -> None:
    aws = FakeAws(candidate=candidate_version(), environment_version=SOURCE_VERSION)
    aws.fail_update = True

    with pytest.raises(RuntimeError, match="original update failure"):
        CandidatePromoter(aws, contract()).run()

    updates = [call for call in aws.calls if "update-environment" in " ".join(call)]
    assert len(updates) == 1
    assert any("describe-events" in " ".join(call) for call in aws.calls)


def test_degraded_target_executes_one_atomic_rollback_with_legacy_contract() -> None:
    aws = FakeAws(candidate=candidate_version(), environment_version=SOURCE_VERSION)
    aws.corrupt_target_contract = True

    with pytest.raises(RuntimeError, match="target domain contract mismatch"):
        CandidatePromoter(aws, contract()).run()

    updates = [call for call in aws.calls if "update-environment" in " ".join(call)]
    assert len(updates) == 2
    rollback = updates[1]
    assert rollback[rollback.index("--version-label") + 1] == SOURCE_VERSION
    assert "--options-to-remove" in rollback
    assert rollback[rollback.index("--options-to-remove") + 1] == (
        "Namespace=aws:elasticbeanstalk:application:environment,"
        "OptionName=TPI_ROUTE53_HOSTED_ZONE_ID"
    )
    assert aws.environment_contract == SOURCE_DEV_ENVIRONMENT


def test_legacy_source_exception_cannot_be_reused_for_another_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "AWS_ACCOUNT_ID": "821656895812",
        "AWS_REGION": "us-east-2",
        "APPLICATION": "tpi-backoffice",
        "ENVIRONMENT": "tpi-backoffice-dev-green",
        "EXPECTED_CURRENT_VERSION": SOURCE_VERSION,
        "VERSION_LABEL": "h3-3-crm-web-future-r1",
        "APPROVED_BUNDLE_BUCKET": "bucket",
        "APPROVED_BUNDLE_KEY": "key",
        "ARTIFACT_DIR": "artifact",
        "BUNDLE_NAME": "bundle.zip",
        "SOURCE_SHA": "0" * 40,
        "BUNDLE_SHA256": "0" * 64,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match="authorized H3.3 cutover"):
        PromotionContract.from_environment()
