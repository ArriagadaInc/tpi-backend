"""Idempotent promotion of one immutable DEV candidate to Elastic Beanstalk."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class AwsCommandError(RuntimeError):
    """Raised when an AWS CLI command fails."""


class AwsCli(Protocol):
    def json(self, *arguments: str) -> object: ...


class SubprocessAwsCli:
    def json(self, *arguments: str) -> object:
        command = ["aws", *arguments, "--output", "json"]
        result = subprocess.run(command, capture_output=True, check=False, text=True)  # noqa: S603
        if result.returncode != 0:
            message = result.stderr.strip() or "AWS CLI command failed"
            raise AwsCommandError(message)
        return json.loads(result.stdout)


@dataclass(frozen=True)
class PromotionContract:
    account_id: str
    region: str
    application: str
    environment: str
    current_version: str
    candidate_version: str
    approved_bundle_bucket: str
    approved_bundle_key: str
    legacy_bundle_bucket: str
    legacy_bundle_key: str
    artifact_dir: str
    bundle_name: str
    runtime_sha: str
    bundle_sha256: str

    @classmethod
    def from_environment(cls) -> PromotionContract:
        names = {
            "account_id": "AWS_ACCOUNT_ID",
            "region": "AWS_REGION",
            "application": "APPLICATION",
            "environment": "ENVIRONMENT",
            "current_version": "EXPECTED_CURRENT_VERSION",
            "candidate_version": "VERSION_LABEL",
            "approved_bundle_bucket": "APPROVED_BUNDLE_BUCKET",
            "approved_bundle_key": "APPROVED_BUNDLE_KEY",
            "legacy_bundle_bucket": "LEGACY_BUNDLE_BUCKET",
            "legacy_bundle_key": "LEGACY_BUNDLE_KEY",
            "artifact_dir": "ARTIFACT_DIR",
            "bundle_name": "BUNDLE_NAME",
            "runtime_sha": "SOURCE_SHA",
            "bundle_sha256": "BUNDLE_SHA256",
        }
        missing = [variable for variable in names.values() if not os.getenv(variable)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        return cls(**{field: os.environ[variable] for field, variable in names.items()})


class CandidatePromoter:
    def __init__(self, aws: AwsCli, contract: PromotionContract) -> None:
        self.aws = aws
        self.contract = contract
        self.update_requested = False

    def run(self) -> None:
        try:
            self._verify_account()
            environment = self._environment()
            self._ensure_candidate()
            self._verify_rollback()

            if self._is_healthy(environment, self.contract.candidate_version):
                print("Candidate is already deployed and healthy; continuing to postflight.")
            else:
                self._require_healthy(environment, self.contract.current_version)
                self.update_requested = True
                self.aws.json(
                    "elasticbeanstalk",
                    "update-environment",
                    "--region",
                    self.contract.region,
                    "--application-name",
                    self.contract.application,
                    "--environment-name",
                    self.contract.environment,
                    "--version-label",
                    self.contract.candidate_version,
                )
                self._wait_for_healthy_candidate()

            self._verify_rollback()
            self._require_healthy(self._environment(), self.contract.candidate_version)
        except Exception:
            self._show_events()
            raise

    def _verify_account(self) -> None:
        identity = self.aws.json("sts", "get-caller-identity")
        if not isinstance(identity, dict) or identity.get("Account") != self.contract.account_id:
            raise RuntimeError("AWS account does not match the promotion contract")

    def _environment(self) -> dict[str, object]:
        response = self.aws.json(
            "elasticbeanstalk",
            "describe-environments",
            "--region",
            self.contract.region,
            "--application-name",
            self.contract.application,
            "--environment-names",
            self.contract.environment,
            "--no-include-deleted",
        )
        environments = response.get("Environments", []) if isinstance(response, dict) else []
        if len(environments) != 1 or not isinstance(environments[0], dict):
            raise RuntimeError("Expected exactly one approved Elastic Beanstalk environment")
        environment = environments[0]
        if (
            environment.get("ApplicationName") != self.contract.application
            or environment.get("EnvironmentName") != self.contract.environment
        ):
            raise RuntimeError("Elastic Beanstalk environment identity mismatch")
        return environment

    def _versions(self, version_label: str) -> list[dict[str, object]]:
        response = self.aws.json(
            "elasticbeanstalk",
            "describe-application-versions",
            "--region",
            self.contract.region,
            "--application-name",
            self.contract.application,
            "--version-labels",
            version_label,
        )
        versions = response.get("ApplicationVersions", []) if isinstance(response, dict) else []
        if not isinstance(versions, list) or not all(isinstance(item, dict) for item in versions):
            raise RuntimeError("Unexpected Elastic Beanstalk application version response")
        return versions

    def _ensure_candidate(self) -> None:
        versions = self._versions(self.contract.candidate_version)
        if not versions:
            self._materialize_approved_bundle()
            self.aws.json(
                "elasticbeanstalk",
                "create-application-version",
                "--region",
                self.contract.region,
                "--application-name",
                self.contract.application,
                "--version-label",
                self.contract.candidate_version,
                "--source-bundle",
                (
                    f"S3Bucket={self.contract.approved_bundle_bucket},"
                    f"S3Key={self.contract.approved_bundle_key}"
                ),
                "--no-process",
                "--no-auto-create-application",
            )
            versions = self._wait_for_candidate()
        if len(versions) != 1:
            raise RuntimeError("Candidate application version must exist exactly once")
        self._verify_candidate(versions[0])

    def _materialize_approved_bundle(self) -> None:
        bundle = Path(self.contract.artifact_dir) / self.contract.bundle_name
        if not bundle.is_file():
            raise RuntimeError("Verified candidate bundle is unavailable")
        with bundle.open("rb") as bundle_stream:
            bundle_hash = hashlib.file_digest(bundle_stream, "sha256")
        actual_sha256 = bundle_hash.hexdigest()
        if not hmac.compare_digest(actual_sha256, self.contract.bundle_sha256):
            raise RuntimeError("Verified candidate bundle SHA256 mismatch")

        checksum = base64.b64encode(bundle_hash.digest()).decode("ascii")
        self.aws.json(
            "s3api",
            "put-object",
            "--region",
            self.contract.region,
            "--bucket",
            self.contract.approved_bundle_bucket,
            "--key",
            self.contract.approved_bundle_key,
            "--body",
            str(bundle),
            "--content-type",
            "application/zip",
            "--checksum-algorithm",
            "SHA256",
            "--checksum-sha256",
            checksum,
            "--metadata",
            (
                f"runtime-git-sha={self.contract.runtime_sha},"
                f"bundle-sha256={self.contract.bundle_sha256}"
            ),
        )
        self._verify_approved_bundle_checksum(checksum)

    def _verify_approved_bundle_checksum(self, expected_checksum: str | None = None) -> None:
        checksum = expected_checksum or self._expected_s3_checksum()
        response = self.aws.json(
            "s3api",
            "head-object",
            "--region",
            self.contract.region,
            "--bucket",
            self.contract.approved_bundle_bucket,
            "--key",
            self.contract.approved_bundle_key,
            "--checksum-mode",
            "ENABLED",
        )
        stored_checksum = response.get("ChecksumSHA256") if isinstance(response, dict) else None
        if stored_checksum != checksum:
            raise RuntimeError("Approved release object checksum mismatch")

    def _verify_legacy_bundle_bytes(self) -> None:
        destination = Path(self.contract.artifact_dir) / ".legacy-source-bundle.zip"
        destination.unlink(missing_ok=True)
        try:
            self.aws.json(
                "s3api",
                "get-object",
                "--region",
                self.contract.region,
                "--bucket",
                self.contract.legacy_bundle_bucket,
                "--key",
                self.contract.legacy_bundle_key,
                str(destination),
            )
            if not destination.is_file():
                raise RuntimeError("Legacy SourceBundle download did not produce a file")
            with destination.open("rb") as source_stream:
                actual_sha256 = hashlib.file_digest(source_stream, "sha256").hexdigest()
            if not hmac.compare_digest(actual_sha256, self.contract.bundle_sha256):
                raise RuntimeError("Legacy SourceBundle SHA256 mismatch")
        finally:
            destination.unlink(missing_ok=True)

    def _expected_s3_checksum(self) -> str:
        try:
            digest = bytes.fromhex(self.contract.bundle_sha256)
        except ValueError as error:
            raise RuntimeError("Bundle SHA256 contract is invalid") from error
        if len(digest) != hashlib.sha256().digest_size:
            raise RuntimeError("Bundle SHA256 contract is invalid")
        return base64.b64encode(digest).decode("ascii")

    def _wait_for_candidate(self) -> list[dict[str, object]]:
        for _ in range(30):
            versions = self._versions(self.contract.candidate_version)
            if versions:
                status = versions[0].get("Status")
                if status == "FAILED":
                    raise RuntimeError("Candidate application version is FAILED")
                if status in {"UNPROCESSED", "PROCESSED"}:
                    return versions
            time.sleep(10)
        raise TimeoutError("Timed out waiting for candidate application version")

    def _verify_candidate(self, version: dict[str, object]) -> None:
        if version.get("VersionLabel") != self.contract.candidate_version:
            raise RuntimeError("Candidate application version label mismatch")
        if version.get("Status") == "FAILED":
            raise RuntimeError("Candidate application version is FAILED")
        source = version.get("SourceBundle")
        if not isinstance(source, dict):
            raise RuntimeError("Candidate application version has no SourceBundle")
        actual = (source.get("S3Bucket"), source.get("S3Key"))
        approved = (self.contract.approved_bundle_bucket, self.contract.approved_bundle_key)
        legacy = (self.contract.legacy_bundle_bucket, self.contract.legacy_bundle_key)
        if actual == approved:
            self._verify_approved_bundle_checksum()
        elif actual == legacy:
            self._verify_legacy_bundle_bytes()
        else:
            raise RuntimeError("Candidate SourceBundle does not match an approved immutable source")

    def _verify_rollback(self) -> None:
        versions = self._versions(self.contract.current_version)
        if len(versions) != 1:
            raise RuntimeError("Known-good rollback version must exist exactly once")
        version = versions[0]
        if version.get("VersionLabel") != self.contract.current_version:
            raise RuntimeError("Known-good rollback version label mismatch")
        if version.get("Status") == "FAILED" or version.get("SourceBundle") is None:
            raise RuntimeError("Known-good rollback version is not usable")

    @staticmethod
    def _is_healthy(environment: dict[str, object], version: str) -> bool:
        return (
            environment.get("VersionLabel") == version
            and environment.get("Status") == "Ready"
            and environment.get("Health") == "Green"
            and environment.get("HealthStatus") == "Ok"
        )

    def _require_healthy(self, environment: dict[str, object], version: str) -> None:
        if not self._is_healthy(environment, version):
            raise RuntimeError(f"Environment is not healthy on required version {version}")

    def _wait_for_healthy_candidate(self) -> None:
        for _ in range(60):
            environment = self._environment()
            if self._is_healthy(environment, self.contract.candidate_version):
                return
            time.sleep(30)
        raise TimeoutError("Timed out waiting for Ready/Green/Ok candidate deployment")

    def _show_events(self) -> None:
        try:
            events = self.aws.json(
                "elasticbeanstalk",
                "describe-events",
                "--region",
                self.contract.region,
                "--application-name",
                self.contract.application,
                "--environment-name",
                self.contract.environment,
                "--max-records",
                "20",
            )
            print("Recent Elastic Beanstalk events:", json.dumps(events, default=str))
        except Exception as diagnostic_error:  # noqa: BLE001
            print(
                f"Unable to collect Elastic Beanstalk events: {diagnostic_error}", file=sys.stderr
            )


def main() -> int:
    try:
        CandidatePromoter(SubprocessAwsCli(), PromotionContract.from_environment()).run()
    except Exception as error:  # noqa: BLE001
        print(f"Promotion failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
