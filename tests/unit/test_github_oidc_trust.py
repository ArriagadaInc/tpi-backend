from __future__ import annotations

import json
from pathlib import Path

TRUST_POLICY_PATH = Path("deployment/iam/tpi-github-actions-dev-ecr-role-trust.json")
EXPECTED_SUBJECT = "repo:ArriagadaInc@37077654/tpi-backend@1318709295:ref:refs/heads/main"


def test_github_actions_trust_policy_is_restricted_to_main() -> None:
    policy = json.loads(TRUST_POLICY_PATH.read_text(encoding="utf-8"))
    statement = policy["Statement"]
    assert len(statement) == 1

    rule = statement[0]
    assert rule["Principal"] == {
        "Federated": "arn:aws:iam::821656895812:oidc-provider/"
        "token.actions.githubusercontent.com"
    }
    assert rule["Action"] == "sts:AssumeRoleWithWebIdentity"
    assert set(rule["Condition"]) == {"StringEquals"}

    conditions = rule["Condition"]["StringEquals"]
    assert conditions["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    assert conditions["token.actions.githubusercontent.com:sub"] == EXPECTED_SUBJECT
    assert "*" not in json.dumps(policy)
    assert "feat/h2-5-simple-dev-auth" not in json.dumps(policy)
