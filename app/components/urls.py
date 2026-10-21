"""Approved public navigation URLs shared by the web and API surfaces."""

from __future__ import annotations

from urllib.parse import urlsplit

from app.config import Settings

_PUBLIC_SITE_BY_ENVIRONMENT = {
    "local": ("http", "tpi.localhost", 8080),
    "aws-dev": ("https", "dev.tupensioninteligente.cl", None),
}


def get_public_site_url(settings: Settings) -> str | None:
    """Return the approved public DEV URL without credentials or query data."""
    expected = _PUBLIC_SITE_BY_ENVIRONMENT.get(settings.normalized_app_env)
    configured_url = settings.public_site_url
    if expected is None or not configured_url:
        return None

    try:
        parsed = urlsplit(configured_url)
        configured_port = parsed.port
    except ValueError:
        return None

    scheme, hostname, port = expected
    if (
        parsed.scheme != scheme
        or parsed.hostname != hostname
        or configured_port != port
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return None

    return configured_url.rstrip("/") + "/"


def get_public_simulator_url(settings: Settings) -> str | None:
    """Return the approved simulator URL derived from the approved public host."""
    public_site_url = get_public_site_url(settings)
    if public_site_url is None:
        return None
    return public_site_url.rstrip("/") + "/simulador.html#simulador-interactivo"
