"""Unit tests for resumable Elastic Beanstalk candidate promotion."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from deployment.aws.promote_eb_candidate import CandidatePromoter, PromotionContract


class FakeAws:
    def __init__(self, *, candidate: dict[str, object] | None, environment_version: str) -> None:
        self.candidate = candidate
        self.environment_version = environment_version
        self.calls: list[tuple[str, ...]] = []
        self.fail_update = False
        self.stored_checksum: str | None = None
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
        if "describe-application-versions" in command:
            label = arguments[arguments.index("--version-labels") + 1]
            if label == "h2-5d-ecr-47fa0c9":
                return {
                    "ApplicationVersions": [
                        {
                            "VersionLabel": label,
                            "Status": "UNPROCESSED",
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
            self.environment_version = "h3-3-crm-web-28cf009-r1"
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
        current_version="h2-5d-ecr-47fa0c9",
        candidate_version="h3-3-crm-web-28cf009-r1",
        approved_bundle_bucket="tpi-dev-release-artifacts-821656895812-us-east-2",
        approved_bundle_key=(
            "approved-releases/h3-3-crm-web-28cf009-r1/"
            "5e998cadee8b2ee08a4fa08f487a8203555c6971da5465427645f66ffb923045.zip"
        ),
        legacy_bundle_bucket="elasticbeanstalk-us-east-2-821656895812",
        legacy_bundle_key=(
            "tpi-backoffice/dev-releases/h3-3-crm-web-28cf009-r1/tpi-dev-ecr-28cf009.zip"
        ),
        artifact_dir="artifact",
        bundle_name="tpi-dev-ecr-28cf009.zip",
        runtime_sha="28cf009137ada707540d9ee7eba01dc45a9a260e",
        bundle_sha256="5e998cadee8b2ee08a4fa08f487a8203555c6971da5465427645f66ffb923045",
    )


def materializable_contract(
    tmp_path: Path, content: bytes = b"verified bundle"
) -> PromotionContract:
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    (artifact_dir / "tpi-dev-ecr-28cf009.zip").write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    return replace(
        contract(),
        artifact_dir=str(artifact_dir),
        bundle_sha256=digest,
        approved_bundle_key=f"approved-releases/h3-3-crm-web-28cf009-r1/{digest}.zip",
    )


def candidate_version(**overrides: Any) -> dict[str, object]:
    value: dict[str, object] = {
        "VersionLabel": "h3-3-crm-web-28cf009-r1",
        "Status": "UNPROCESSED",
        "SourceBundle": {
            "S3Bucket": "tpi-dev-release-artifacts-821656895812-us-east-2",
            "S3Key": (
                "approved-releases/h3-3-crm-web-28cf009-r1/"
                "5e998cadee8b2ee08a4fa08f487a8203555c6971da5465427645f66ffb923045.zip"
            ),
        },
    }
    value.update(overrides)
    return value


def test_candidate_is_created_from_materialized_verified_bundle_when_absent(tmp_path: Path) -> None:
    aws = FakeAws(candidate=None, environment_version="h2-5d-ecr-47fa0c9")
    promotion_contract = materializable_contract(tmp_path)

    CandidatePromoter(aws, promotion_contract).run()

    commands = list(map(" ".join, aws.calls))
    put_index = next(index for index, call in enumerate(commands) if "s3api put-object" in call)
    create_index = next(
        index for index, call in enumerate(commands) if "create-application-version" in call
    )
    assert put_index < create_index
    expected_checksum = base64.b64encode(hashlib.sha256(b"verified bundle").digest()).decode()
    assert aws.stored_checksum == expected_checksum
    assert promotion_contract.approved_bundle_key in commands[put_index]
    assert promotion_contract.approved_bundle_key in commands[create_index]
    assert aws.environment_version == "h3-3-crm-web-28cf009-r1"


def test_incorrect_bundle_bytes_cannot_be_materialized_even_with_plausible_metadata(
    tmp_path: Path,
) -> None:
    promotion_contract = materializable_contract(tmp_path, b"incorrect bytes")
    promotion_contract = replace(
        promotion_contract,
        bundle_sha256="5e998cadee8b2ee08a4fa08f487a8203555c6971da5465427645f66ffb923045",
    )
    aws = FakeAws(candidate=None, environment_version="h2-5d-ecr-47fa0c9")

    with pytest.raises(RuntimeError, match="bundle SHA256 mismatch"):
        CandidatePromoter(aws, promotion_contract).run()

    commands = [" ".join(call) for call in aws.calls]
    assert not any("s3api put-object" in call for call in commands)
    assert not any("create-application-version" in call for call in commands)


def test_storage_checksum_mismatch_aborts_before_application_version_creation(
    tmp_path: Path,
) -> None:
    promotion_contract = materializable_contract(tmp_path)
    aws = FakeAws(candidate=None, environment_version="h2-5d-ecr-47fa0c9")
    aws.head_checksum_override = "different-stored-bytes"

    with pytest.raises(RuntimeError, match="object checksum mismatch"):
        CandidatePromoter(aws, promotion_contract).run()

    commands = [" ".join(call) for call in aws.calls]
    assert any("s3api put-object" in call for call in commands)
    assert not any("create-application-version" in call for call in commands)


def test_matching_existing_candidate_is_reused() -> None:
    aws = FakeAws(candidate=candidate_version(), environment_version="h2-5d-ecr-47fa0c9")

    CandidatePromoter(aws, contract()).run()

    commands = [" ".join(call) for call in aws.calls]
    assert not any("create-application-version" in call for call in commands)
    assert sum("update-environment" in call for call in commands) == 1


def test_matching_existing_legacy_candidate_is_reused() -> None:
    legacy = candidate_version(
        SourceBundle={
            "S3Bucket": "elasticbeanstalk-us-east-2-821656895812",
            "S3Key": (
                "tpi-backoffice/dev-releases/h3-3-crm-web-28cf009-r1/tpi-dev-ecr-28cf009.zip"
            ),
        }
    )
    aws = FakeAws(candidate=legacy, environment_version="h2-5d-ecr-47fa0c9")

    CandidatePromoter(aws, contract()).run()

    commands = [" ".join(call) for call in aws.calls]
    assert not any("create-application-version" in call for call in commands)
    assert sum("update-environment" in call for call in commands) == 1


def test_mismatched_existing_candidate_aborts_before_update() -> None:
    mismatched = candidate_version(SourceBundle={"S3Bucket": "unexpected", "S3Key": "other.zip"})
    aws = FakeAws(candidate=mismatched, environment_version="h2-5d-ecr-47fa0c9")

    with pytest.raises(RuntimeError, match="SourceBundle"):
        CandidatePromoter(aws, contract()).run()

    assert not any("update-environment" in " ".join(call) for call in aws.calls)


def test_already_deployed_candidate_continues_to_postflight_without_update() -> None:
    aws = FakeAws(candidate=candidate_version(), environment_version="h3-3-crm-web-28cf009-r1")

    CandidatePromoter(aws, contract()).run()

    assert not any("update-environment" in " ".join(call) for call in aws.calls)


def test_update_failure_keeps_original_error_and_collects_events(
    capsys: pytest.CaptureFixture[str],
) -> None:
    aws = FakeAws(candidate=candidate_version(), environment_version="h2-5d-ecr-47fa0c9")
    aws.fail_update = True

    with pytest.raises(RuntimeError, match="original update failure"):
        CandidatePromoter(aws, contract()).run()

    assert any("describe-events" in " ".join(call) for call in aws.calls)
    assert "diagnostic event" in capsys.readouterr().out
