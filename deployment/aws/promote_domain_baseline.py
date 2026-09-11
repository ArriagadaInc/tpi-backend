"""One-shot H3.3 phase-1 domain-baseline promotion (28cf009 -> baseline + TPI domain)."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
from typing import Final, Protocol

ACCOUNT_ID: Final = "821656895812"
REGION: Final = "us-east-2"
APPLICATION: Final = "tpi-backoffice"
ENVIRONMENT: Final = "tpi-backoffice-dev-green"
SOURCE_VERSION: Final = "h3-3-crm-web-28cf009-r1"
TARGET_VERSION: Final = "h3-3-domain-baseline-28cf009-caddy43101be-r1"

BASELINE_BUCKET: Final = "tpi-dev-release-artifacts-821656895812-us-east-2"
BASELINE_KEY: Final = (
    "approved-releases/h3-3-domain-baseline-28cf009-caddy43101be-r1/"
    "e1393c10850956b8921a0bab66d11447beadce89ef6bcf7aaf34f513435017d9.zip"
)
BASELINE_VERSION_ID: Final = "hLIqFICeoJj.JxgcMU_Yii_1wCvHQNQ3"
BASELINE_SHA256: Final = "e1393c10850956b8921a0bab66d11447beadce89ef6bcf7aaf34f513435017d9"
BASELINE_APP_GIT_SHA: Final = "28cf009137ada707540d9ee7eba01dc45a9a260e"
BASELINE_CADDY_GIT_SHA: Final = "43101be7835088f93267bee85b0f11c8bc879867"

ENVIRONMENT_NAMESPACE: Final = "aws:elasticbeanstalk:application:environment"

# Phase-1 emergency rollback only: the legacy source contract. genialabs.cl stops
# being an authorized rollback once the TPI baseline is deployed and validated.
SOURCE_DEV_ENVIRONMENT: Final = {
    "TPI_PUBLIC_SITE_URL": "https://dev.genialabs.cl/",
    "TPI_PUBLIC_SITE_ADDRESS": "https://dev.genialabs.cl",
    "TPI_BACKOFFICE_SITE_ADDRESS": "https://backoffice.dev.genialabs.cl",
}
TARGET_DEV_ENVIRONMENT: Final = {
    "TPI_PUBLIC_SITE_URL": "https://dev.tupensioninteligente.cl/",
    "TPI_PUBLIC_SITE_ADDRESS": "https://dev.tupensioninteligente.cl",
    "TPI_BACKOFFICE_SITE_ADDRESS": "https://backoffice.dev.tupensioninteligente.cl",
    "TPI_ROUTE53_HOSTED_ZONE_ID": "Z07053592LX0W8GJXNI1C",
}
EXPECTED_METADATA: Final = {
    "artifact-type": "domain-baseline",
    "app-git-sha": BASELINE_APP_GIT_SHA,
    "caddy-git-sha": BASELINE_CADDY_GIT_SHA,
    "bundle-sha256": BASELINE_SHA256,
}


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


class BaselinePromoter:
    def __init__(self, aws: AwsCli) -> None:
        self.aws = aws
        self.environment_update_accepted = False

    def run(self) -> None:
        try:
            self._verify_account()
            environment = self._environment()
            self._require_healthy(environment, SOURCE_VERSION)
            self._verify_baseline_object()
            self._ensure_target_version()
            self._verify_rollback()
            self._promote_atomically()
            self._wait_for_healthy_version(TARGET_VERSION)
            self._verify_rollback()
            self._require_healthy(self._environment(), TARGET_VERSION)
        except Exception:
            try:
                self._rollback_if_environment_is_degraded()
            except Exception as rollback_error:  # noqa: BLE001
                print(
                    f"Atomic rollback failed after promotion failure: {rollback_error}",
                    file=sys.stderr,
                )
            self._show_events()
            raise

    def _verify_account(self) -> None:
        identity = self.aws.json("sts", "get-caller-identity")
        if not isinstance(identity, dict) or identity.get("Account") != ACCOUNT_ID:
            raise RuntimeError("AWS account does not match the baseline contract")

    def _environment(self) -> dict[str, object]:
        response = self.aws.json(
            "elasticbeanstalk",
            "describe-environments",
            "--region",
            REGION,
            "--application-name",
            APPLICATION,
            "--environment-names",
            ENVIRONMENT,
            "--no-include-deleted",
        )
        environments = response.get("Environments", []) if isinstance(response, dict) else []
        if len(environments) != 1 or not isinstance(environments[0], dict):
            raise RuntimeError("Expected exactly one approved Elastic Beanstalk environment")
        environment = environments[0]
        if (
            environment.get("ApplicationName") != APPLICATION
            or environment.get("EnvironmentName") != ENVIRONMENT
        ):
            raise RuntimeError("Elastic Beanstalk environment identity mismatch")
        return environment

    def _verify_baseline_object(self) -> None:
        response = self.aws.json(
            "s3api",
            "head-object",
            "--region",
            REGION,
            "--bucket",
            BASELINE_BUCKET,
            "--key",
            BASELINE_KEY,
            "--checksum-mode",
            "ENABLED",
        )
        if not isinstance(response, dict):
            raise RuntimeError("Unexpected baseline object response")
        if response.get("VersionId") != BASELINE_VERSION_ID:
            raise RuntimeError("Baseline S3 VersionId does not match the authorized object")
        expected_checksum = base64.b64encode(bytes.fromhex(BASELINE_SHA256)).decode("ascii")
        if response.get("ChecksumSHA256") != expected_checksum:
            raise RuntimeError("Baseline S3 checksum does not match the authorized object")
        if response.get("Metadata") != EXPECTED_METADATA:
            raise RuntimeError("Baseline S3 metadata does not match the authorized object")

    def _versions(self, version_label: str) -> list[dict[str, object]]:
        response = self.aws.json(
            "elasticbeanstalk",
            "describe-application-versions",
            "--region",
            REGION,
            "--application-name",
            APPLICATION,
            "--version-labels",
            version_label,
        )
        versions = response.get("ApplicationVersions", []) if isinstance(response, dict) else []
        if not isinstance(versions, list) or not all(isinstance(item, dict) for item in versions):
            raise RuntimeError("Unexpected Elastic Beanstalk application version response")
        return versions

    def _ensure_target_version(self) -> None:
        versions = self._versions(TARGET_VERSION)
        if not versions:
            self.aws.json(
                "elasticbeanstalk",
                "create-application-version",
                "--region",
                REGION,
                "--application-name",
                APPLICATION,
                "--version-label",
                TARGET_VERSION,
                "--source-bundle",
                f"S3Bucket={BASELINE_BUCKET},S3Key={BASELINE_KEY}",
                "--no-process",
                "--no-auto-create-application",
            )
            versions = self._wait_for_target_version()
        if len(versions) != 1:
            raise RuntimeError("Target application version must exist exactly once")
        self._verify_target_version(versions[0])

    def _wait_for_target_version(self) -> list[dict[str, object]]:
        for _ in range(30):
            versions = self._versions(TARGET_VERSION)
            if versions:
                status = versions[0].get("Status")
                if status == "FAILED":
                    raise RuntimeError("Target application version is FAILED")
                if status in {"UNPROCESSED", "PROCESSED"}:
                    return versions
            time.sleep(10)
        raise TimeoutError("Timed out waiting for target application version")

    def _verify_target_version(self, version: dict[str, object]) -> None:
        if version.get("VersionLabel") != TARGET_VERSION:
            raise RuntimeError("Target application version label mismatch")
        if version.get("Status") == "FAILED":
            raise RuntimeError("Target application version is FAILED")
        source = version.get("SourceBundle")
        if not isinstance(source, dict):
            raise RuntimeError("Target application version has no SourceBundle")
        if (source.get("S3Bucket"), source.get("S3Key")) != (BASELINE_BUCKET, BASELINE_KEY):
            raise RuntimeError("Target SourceBundle does not match the authorized baseline object")

    def _verify_rollback(self) -> None:
        versions = self._versions(SOURCE_VERSION)
        if len(versions) != 1:
            raise RuntimeError("Known-good rollback version must exist exactly once")
        version = versions[0]
        if version.get("VersionLabel") != SOURCE_VERSION:
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

    @staticmethod
    def _option_settings(values: dict[str, str]) -> tuple[str, ...]:
        return tuple(
            f"Namespace={ENVIRONMENT_NAMESPACE},OptionName={name},Value={value}"
            for name, value in values.items()
        )

    def _update_environment(
        self, version: str, values: dict[str, str], *, remove_hosted_zone_id: bool
    ) -> None:
        arguments = [
            "elasticbeanstalk",
            "update-environment",
            "--region",
            REGION,
            "--application-name",
            APPLICATION,
            "--environment-name",
            ENVIRONMENT,
            "--version-label",
            version,
            "--option-settings",
            *self._option_settings(values),
        ]
        if remove_hosted_zone_id:
            arguments.extend(
                [
                    "--options-to-remove",
                    f"Namespace={ENVIRONMENT_NAMESPACE},OptionName=TPI_ROUTE53_HOSTED_ZONE_ID",
                ]
            )
        self.aws.json(*arguments)

    def _promote_atomically(self) -> None:
        self._update_environment(
            TARGET_VERSION, TARGET_DEV_ENVIRONMENT, remove_hosted_zone_id=False
        )
        self.environment_update_accepted = True

    def _wait_for_healthy_version(self, version: str) -> None:
        for _ in range(60):
            environment = self._environment()
            if self._is_healthy(environment, version):
                return
            time.sleep(30)
        raise TimeoutError(f"Timed out waiting for Ready/Green/Ok deployment of {version}")

    def _rollback_if_environment_is_degraded(self) -> None:
        if not self.environment_update_accepted:
            return
        environment = self._environment()
        if self._is_healthy(environment, SOURCE_VERSION):
            return
        if self._is_healthy(environment, TARGET_VERSION):
            return

        print(
            "Environment is degraded after the accepted promotion; "
            "executing phase-1 legacy rollback."
        )
        self._update_environment(SOURCE_VERSION, SOURCE_DEV_ENVIRONMENT, remove_hosted_zone_id=True)
        self._wait_for_healthy_version(SOURCE_VERSION)

    def _show_events(self) -> None:
        try:
            events = self.aws.json(
                "elasticbeanstalk",
                "describe-events",
                "--region",
                REGION,
                "--application-name",
                APPLICATION,
                "--environment-name",
                ENVIRONMENT,
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
        BaselinePromoter(SubprocessAwsCli()).run()
    except Exception as error:  # noqa: BLE001
        print(f"Promotion failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
