"""Unit coverage for the private-to-public DEV navigation control."""

from __future__ import annotations

import pytest

from app.components.urls import get_public_simulator_url, get_public_site_url
from app.config import Settings


@pytest.mark.parametrize(
    ("app_env", "configured_url", "expected"),
    [
        ("local", "http://tpi.localhost:8080/", "http://tpi.localhost:8080/"),
        (
            "aws-dev",
            "https://dev.tupensioninteligente.cl/",
            "https://dev.tupensioninteligente.cl/",
        ),
    ],
)
def test_public_site_link_uses_the_approved_environment_url(
    app_env: str, configured_url: str, expected: str
) -> None:
    settings = Settings(_env_file=None, APP_ENV=app_env, TPI_PUBLIC_SITE_URL=configured_url)

    assert get_public_site_url(settings) == expected


@pytest.mark.parametrize(
    ("app_env", "configured_url"),
    [
        ("production", "https://tupensioninteligente.cl/"),
        ("local", "https://tpi.localhost:8080/"),
        ("local", "http://tpi.localhost:8080/?token=unsafe"),
        ("local", "http://tpi.localhost:not-a-port/"),
        ("aws-dev", "https://user:password@dev.tupensioninteligente.cl/"),
        ("aws-dev", "https://unapproved.example/"),
    ],
)
def test_public_site_link_is_hidden_when_configuration_is_not_an_approved_dev_url(
    app_env: str, configured_url: str
) -> None:
    settings = Settings(_env_file=None, APP_ENV=app_env, TPI_PUBLIC_SITE_URL=configured_url)

    assert get_public_site_url(settings) is None


def test_public_simulator_url_is_derived_from_the_approved_base_url() -> None:
    settings = Settings(
        _env_file=None,
        APP_ENV="aws-dev",
        TPI_PUBLIC_SITE_URL="https://dev.tupensioninteligente.cl/",
    )

    assert get_public_simulator_url(settings) == (
        "https://dev.tupensioninteligente.cl/simulador.html#simulador-interactivo"
    )


def test_public_simulator_url_is_hidden_when_public_site_is_not_approved() -> None:
    settings = Settings(
        _env_file=None, APP_ENV="aws-dev", TPI_PUBLIC_SITE_URL="https://example.com/"
    )

    assert get_public_simulator_url(settings) is None
