"""Security regression tests for H2.5 deployment and auth boundaries."""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_auth_iam_policy_has_only_exact_secret_read_permission() -> None:
    policy_path = PROJECT_ROOT / "deployment/iam/tpi-backoffice-dev-read-auth-users-secret.json"
    statement = json.loads(policy_path.read_text(encoding="utf-8"))["Statement"][0]

    assert statement["Action"] == "secretsmanager:GetSecretValue"
    assert statement["Resource"] == "<SET_EXACT_TPI_DEV_AUTH_USERS_SECRET_ARN_DURING_DEPLOYMENT>"
    assert "*" not in statement["Resource"]


def test_auth_runtime_artifacts_do_not_reference_admin_database_secret() -> None:
    auth_files = [
        PROJECT_ROOT / "app/auth/simple_dev.py",
        PROJECT_ROOT / "deployment/iam/tpi-backoffice-dev-read-auth-users-secret.json",
        PROJECT_ROOT / "docker-compose.yml",
    ]

    assert all(
        "database-admin-password" not in path.read_text(encoding="utf-8") for path in auth_files
    )


def test_compose_exposes_only_caddy_web_ports() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert '"80:80"' in compose
    assert '"443:443"' in compose
    assert '"8501:8501"' not in compose
    assert '"5432:5432"' not in compose


def test_caddy_proxies_only_to_the_internal_streamlit_service() -> None:
    caddyfile = (PROJECT_ROOT / "deployment/caddy/Caddyfile").read_text(encoding="utf-8")

    assert "{$TPI_DEV_DOMAIN}" in caddyfile
    assert "reverse_proxy streamlit:8501" in caddyfile
    assert "http://" not in caddyfile
