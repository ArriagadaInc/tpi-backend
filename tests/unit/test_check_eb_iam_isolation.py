from __future__ import annotations

import pytest

from deployment.aws.check_eb_iam_isolation import EbIdentity, check_isolation


@pytest.mark.parametrize(
    ("blue", "green"),
    [
        (
            EbIdentity(instance_profile="blue-profile", role="blue-role"),
            EbIdentity(instance_profile="green-profile", role="green-role"),
        ),
    ],
)
def test_iam_isolation_passes_for_distinct_profiles_and_roles(
    blue: EbIdentity, green: EbIdentity, capsys
) -> None:
    assert check_isolation(blue, green) is True
    out = capsys.readouterr().out
    assert "IAM isolation: PASS" in out


@pytest.mark.parametrize(
    ("blue", "green"),
    [
        (
            EbIdentity(instance_profile="same-profile", role="blue-role"),
            EbIdentity(instance_profile="same-profile", role="green-role"),
        ),
    ],
)
def test_iam_isolation_fails_for_shared_instance_profile(
    blue: EbIdentity, green: EbIdentity, capsys
) -> None:
    assert check_isolation(blue, green) is False
    out = capsys.readouterr().out
    assert "IAM isolation: FAIL" in out


@pytest.mark.parametrize(
    ("blue", "green"),
    [
        (
            EbIdentity(instance_profile="blue-profile", role="same-role"),
            EbIdentity(instance_profile="green-profile", role="same-role"),
        ),
    ],
)
def test_iam_isolation_fails_for_shared_role(blue: EbIdentity, green: EbIdentity, capsys) -> None:
    assert check_isolation(blue, green) is False
    out = capsys.readouterr().out
    assert "IAM isolation: FAIL" in out
