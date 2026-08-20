"""Fail closed if BLUE and GREEN Elastic Beanstalk environments share IAM identity."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, TypedDict, cast


@dataclass(frozen=True)
class EbIdentity:
    instance_profile: str
    role: str


class _InstanceProfileRole(TypedDict):
    RoleName: str


class _InstanceProfileData(TypedDict):
    Roles: list[_InstanceProfileRole]


class _GetInstanceProfileResponse(TypedDict):
    InstanceProfile: _InstanceProfileData


class _ConfigurationSetting(TypedDict, total=False):
    Namespace: str
    OptionName: str
    Value: str


class _ConfigurationSettingsResponse(TypedDict):
    ConfigurationSettings: list[dict[str, Any]]


def _aws_json(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return cast(dict[str, Any], json.loads(result.stdout))


def _extract_instance_profile(*, application_name: str, environment_name: str) -> str:
    response = cast(
        _ConfigurationSettingsResponse,
        _aws_json(
            [
                "aws",
                "elasticbeanstalk",
                "describe-configuration-settings",
                "--application-name",
                application_name,
                "--environment-name",
                environment_name,
                "--profile",
                "tpi-dev",
                "--region",
                "us-east-2",
            ],
        ),
    )
    settings = cast(
        list[_ConfigurationSetting], response["ConfigurationSettings"][0]["OptionSettings"]
    )
    for setting in settings:
        if (
            setting.get("Namespace") == "aws:autoscaling:launchconfiguration"
            and setting.get("OptionName") == "IamInstanceProfile"
        ):
            value = setting.get("Value")
            if not value:
                raise ValueError(f"{environment_name} has no IamInstanceProfile configured.")
            return cast(str, value)
    raise ValueError(f"{environment_name} has no IamInstanceProfile configured.")


def _extract_role(instance_profile_name: str) -> str:
    response = cast(
        _GetInstanceProfileResponse,
        _aws_json(
            [
                "aws",
                "iam",
                "get-instance-profile",
                "--instance-profile-name",
                instance_profile_name,
                "--profile",
                "tpi-dev",
                "--region",
                "us-east-2",
            ],
        ),
    )
    roles = response["InstanceProfile"]["Roles"]
    if len(roles) != 1:
        raise ValueError(f"{instance_profile_name} must contain exactly one IAM role.")
    return roles[0]["RoleName"]


def load_identity(*, application_name: str, environment_name: str) -> EbIdentity:
    instance_profile = _extract_instance_profile(
        application_name=application_name,
        environment_name=environment_name,
    )
    return EbIdentity(instance_profile=instance_profile, role=_extract_role(instance_profile))


def check_isolation(blue: EbIdentity, green: EbIdentity) -> bool:
    print(f"BLUE profile: {blue.instance_profile}")
    print(f"GREEN profile: {green.instance_profile}")
    print(f"BLUE role: {blue.role}")
    print(f"GREEN role: {green.role}")
    isolated = blue.instance_profile != green.instance_profile and blue.role != green.role
    print(f"IAM isolation: {'PASS' if isolated else 'FAIL'}")
    return isolated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blue-environment", default="tpi-backoffice-dev")
    parser.add_argument("--green-environment", default="tpi-backoffice-dev-ecr")
    parser.add_argument("--application-name", default="tpi-backoffice")
    args = parser.parse_args()

    blue = load_identity(
        application_name=args.application_name,
        environment_name=args.blue_environment,
    )
    green = load_identity(
        application_name=args.application_name,
        environment_name=args.green_environment,
    )
    return 0 if check_isolation(blue, green) else 1


if __name__ == "__main__":
    sys.exit(main())
