"""Unit coverage for the private-to-public DEV navigation control."""

from __future__ import annotations

import pytest

from app.components import ui
from app.config import Settings


@pytest.mark.parametrize(
    ("app_env", "configured_url", "expected"),
    [
        ("local", "http://tpi.localhost:8080/", "http://tpi.localhost:8080/"),
        ("aws-dev", "https://tpi-dev-lab.com/", "https://tpi-dev-lab.com/"),
    ],
)
def test_public_site_link_uses_the_approved_environment_url(
    app_env: str, configured_url: str, expected: str
) -> None:
    settings = Settings(_env_file=None, APP_ENV=app_env, TPI_PUBLIC_SITE_URL=configured_url)

    assert ui.get_public_site_url(settings) == expected


@pytest.mark.parametrize(
    ("app_env", "configured_url"),
    [
        ("production", "https://tupensioninteligente.cl/"),
        ("local", "https://tpi.localhost:8080/"),
        ("local", "http://tpi.localhost:8080/?token=unsafe"),
        ("local", "http://tpi.localhost:not-a-port/"),
        ("aws-dev", "https://user:password@tpi-dev-lab.com/"),
        ("aws-dev", "https://unapproved.example/"),
    ],
)
def test_public_site_link_is_hidden_when_configuration_is_not_an_approved_dev_url(
    app_env: str, configured_url: str
) -> None:
    settings = Settings(_env_file=None, APP_ENV=app_env, TPI_PUBLIC_SITE_URL=configured_url)

    assert ui.get_public_site_url(settings) is None


class _Sidebar:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, bool]] = []

    def link_button(self, label: str, url: str, *, use_container_width: bool) -> None:
        self.calls.append((label, url, use_container_width))


class _FakeStreamlit:
    def __init__(self) -> None:
        self.sidebar = _Sidebar()


def test_rendering_public_site_link_does_not_change_authentication_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamlit = _FakeStreamlit()
    monkeypatch.setattr(ui, "st", fake_streamlit)
    settings = Settings(
        _env_file=None,
        APP_ENV="local",
        TPI_PUBLIC_SITE_URL="http://tpi.localhost:8080/",
    )

    ui.render_public_site_link(settings)

    assert fake_streamlit.sidebar.calls == [("Volver al sitio", "http://tpi.localhost:8080/", True)]
