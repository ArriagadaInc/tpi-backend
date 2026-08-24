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

    assert '"${CADDY_BIND_ADDRESS:-127.0.0.1}:${CADDY_HTTP_PORT:-8080}:80"' in compose
    assert '"${CADDY_BIND_ADDRESS:-127.0.0.1}:${CADDY_HTTPS_PORT:-443}:443"' in compose
    assert '"8501:8501"' not in compose
    assert '"5432:5432"' not in compose


def test_beanstalk_bundle_keeps_the_compose_topology() -> None:
    attributes = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert "/docker-compose.yml export-ignore" not in attributes


def test_caddy_routes_public_and_private_hosts_to_internal_services() -> None:
    caddyfile = (PROJECT_ROOT / "deployment/caddy/Caddyfile").read_text(encoding="utf-8")

    assert "{$TPI_PUBLIC_SITE_ADDRESS:http://tpi.localhost}" in caddyfile
    assert "{$TPI_BACKOFFICE_SITE_ADDRESS:http://backoffice.tpi.localhost}" in caddyfile
    assert "handle /api/*" in caddyfile
    assert "reverse_proxy {$TPI_API_UPSTREAM:api:8000}" in caddyfile
    assert "reverse_proxy {$TPI_BACKOFFICE_UPSTREAM:backoffice:8501}" in caddyfile
    assert caddyfile.count('X-Robots-Tag "noindex, nofollow"') == 2


def test_public_api_compose_service_does_not_receive_auth_secret() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    public_section = compose.split("  backoffice:", maxsplit=1)[0]

    assert "AUTH_USERS_JSON" not in public_section
    assert "AUTH_USERS_JSON" in compose.split("  backoffice:", maxsplit=1)[1]


def test_public_api_does_not_receive_the_admin_database_secret_or_open_cors() -> None:
    api_files = [
        PROJECT_ROOT / "app/api/routes.py",
        PROJECT_ROOT / "app/api/app.py",
        PROJECT_ROOT / "docker-compose.yml",
    ]

    contents = "\n".join(path.read_text(encoding="utf-8") for path in api_files)
    assert "database-admin-password" not in contents
    assert "CORSMiddleware" not in contents


def test_aws_dev_compose_runs_fastapi_web_and_cables_web_runtime_secrets() -> None:
    compose = (PROJECT_ROOT / "deployment/aws/docker-compose.ecr.yml").read_text(encoding="utf-8")
    backoffice_section = compose.split("  backoffice:", maxsplit=1)[1]

    assert 'command: ["uvicorn", "app.web.main:app", "--host", "0.0.0.0", "--port", "8501"]' in compose
    assert 'AUTH_ENABLED: ${AUTH_ENABLED:-true}' in backoffice_section
    assert 'AUTH_MODE: ${AUTH_MODE:-simple-dev}' in backoffice_section
    assert (
        'AUTH_USERS_JSON: ${AUTH_USERS_JSON:?AUTH_USERS_JSON is required when authentication is enabled}'
        in backoffice_section
    )
    assert 'WEB_SESSION_SECRET: ${WEB_SESSION_SECRET:?WEB_SESSION_SECRET is required}' in backoffice_section
    assert 'WEB_SESSION_MAX_AGE_SECONDS: ${WEB_SESSION_MAX_AGE_SECONDS:-28800}' in backoffice_section
    assert 'WEB_MASK_PII: ${WEB_MASK_PII:-true}' in backoffice_section
    assert 'TPI_PUBLIC_SITE_URL: ${TPI_PUBLIC_SITE_URL:?TPI_PUBLIC_SITE_URL is required}' in backoffice_section
    assert 'DEV_DELETE_ENABLED: ${DEV_DELETE_ENABLED:-false}' in backoffice_section
    assert "reverse_proxy {$TPI_BACKOFFICE_UPSTREAM:backoffice:8501}" in (PROJECT_ROOT / "deployment/caddy/Caddyfile").read_text(encoding="utf-8")


def test_dockerfile_caches_locked_dependencies_before_application_source() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert dockerfile.index(
        "RUN pip install --no-cache-dir --requirement requirements/runtime.lock"
    ) < (dockerfile.index("COPY --chown=appuser:appuser app ./app"))
