"""H3.3.7 — tema claro y oscuro para CRM Lite.

The theme is client-side only: ``app/web/static/js/theme.js`` sets
``<html data-theme="light|dark">`` from ``localStorage`` and ``app.css`` overrides
the colour tokens under ``[data-theme="dark"]``. These tests cover:

- the server-rendered markup (default light theme, early synchronous script,
  accessible toggle on every page) — AC-1, AC-5;
- the CSS token contract (light tokens unchanged, dark tokens complete, WCAG
  contrast for the dark palette, dark overrides for every hard-coded light
  surface) — AC-2, AC-3;
- the real ``theme.js`` behaviour executed in Node with a fake DOM and storage
  (persistence, fallback, invalid values, unavailable storage) — AC-4, AC-5;
- the absence of any server interaction (AC-6).

The Node tests are skipped only when Node is not installed locally; in CI
(``CI`` env var set, GitHub-hosted runners ship Node) a missing Node fails.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess  # nosec B404 - runs the local Node binary on a repo file only
from pathlib import Path
from typing import Any

import pytest

from tests.unit.test_executive_dashboard_render import _page as _dashboard_page
from tests.unit.test_web_app import _build_client, _login

REPO_ROOT = Path(__file__).resolve().parents[2]
CSS_PATH = REPO_ROOT / "app" / "web" / "static" / "css" / "app.css"
THEME_JS_PATH = REPO_ROOT / "app" / "web" / "static" / "js" / "theme.js"

_LEAD_ID = "11111111-1111-1111-1111-111111111111"

# Light tokens as they were on the H3.3.7 baseline (origin/main@b6df6d7). The
# light theme must keep the current appearance, so these must not change.
_BASELINE_LIGHT_TOKENS = {
    "--bg": "#f8fafc",
    "--surface": "#ffffff",
    "--surface-soft": "#eef4f7",
    "--surface-muted": "#f3f6f8",
    "--text": "#0f172a",
    "--muted": "#64748b",
    "--border": "#d9e2ea",
    "--primary": "#0f172a",
    "--accent": "#0d9488",
    "--accent-soft": "#ecfeff",
    "--success": "#059669",
    "--warning": "#d97706",
    "--info": "#2563eb",
    "--slate": "#475569",
    "--shadow": "0 24px 48px rgba(15, 23, 42, 0.08)",
    "--radius": "22px",
    "--radius-sm": "14px",
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def _block(css: str, selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{(.*?)\}", css, flags=re.S)
    assert match is not None, f"missing CSS block {selector}"
    return match.group(1)


def _tokens(block: str) -> dict[str, str]:
    return {name: value.strip() for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block)}


def _dark_tokens() -> dict[str, str]:
    return _tokens(_block(_css(), '[data-theme="dark"]'))


def _dark_section() -> str:
    css = _css()
    marker = "Tema claro / oscuro (H3.3.7)"
    assert marker in css
    return css[css.index(marker) :]


def _luminance(hex_colour: str) -> float:
    value = hex_colour.lstrip("#")
    channels = [int(value[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(foreground: str, background: str) -> float:
    lighter, darker = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _head(html: str) -> str:
    return html.split("</head>", 1)[0]


def _toggle(html: str) -> str:
    match = re.search(r"<button[^>]*data-theme-toggle[^>]*>.*?</button>", html, flags=re.S)
    assert match is not None, "theme toggle not rendered"
    return match.group(0)


def _rendered_pages() -> dict[str, str]:
    client = _build_client()
    pages = {"login": client.get("/login").text}
    _login(client)
    pages["leads"] = client.get("/leads").text
    pages["detail"] = client.get(f"/leads/{_LEAD_ID}").text
    pages["dashboard"] = _dashboard_page()
    return pages


# --------------------------------------------------------------------------- #
# Markup: control, default theme and early application (AC-1, AC-5)
# --------------------------------------------------------------------------- #


def test_every_page_renders_light_by_default_and_the_theme_toggle() -> None:
    for name, html in _rendered_pages().items():
        assert '<html lang="es" data-theme="light">' in html, name
        toggle = _toggle(html)
        assert 'type="button"' in toggle, name
        assert 'aria-pressed="false"' in toggle, name
        assert "Tema oscuro" in toggle, name


def test_toggle_lives_in_the_topbar_and_outside_any_form() -> None:
    html = _rendered_pages()["detail"]
    topbar = html.split('<header class="topbar">', 1)[1].split("</header>", 1)[0]
    assert "data-theme-toggle" in topbar
    # A button inside a form could submit it; the toggle must never reach the server.
    for form in re.findall(r"<form.*?</form>", html, flags=re.S):
        assert "data-theme-toggle" not in form


def test_theme_script_runs_synchronously_before_the_stylesheet() -> None:
    head = _head(_rendered_pages()["leads"])
    tag = re.search(r'<script[^>]*src="/static/js/theme\.js"[^>]*>', head)
    assert tag is not None
    assert "defer" not in tag.group(0)
    assert "async" not in tag.group(0)
    assert head.index("/static/js/theme.js") < head.index("/static/css/app.css")


def test_theme_script_is_served_as_javascript() -> None:
    response = _build_client().get("/static/js/theme.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"].lower()


# --------------------------------------------------------------------------- #
# CSS token contract (AC-2, AC-3)
# --------------------------------------------------------------------------- #


def test_light_tokens_keep_the_baseline_values() -> None:
    root = _tokens(_block(_css(), ":root"))
    assert root == _BASELINE_LIGHT_TOKENS
    assert "color-scheme: light;" in _block(_css(), ":root")


def test_dark_theme_overrides_every_light_colour_token() -> None:
    dark = _dark_tokens()
    colour_tokens = {
        name for name, value in _BASELINE_LIGHT_TOKENS.items() if value.startswith("#")
    }
    assert colour_tokens <= dark.keys()
    for name in colour_tokens:
        assert dark[name] != _BASELINE_LIGHT_TOKENS[name], name
    assert "color-scheme: dark;" in _block(_css(), '[data-theme="dark"]')


def test_dark_theme_uses_very_dark_backgrounds_and_light_text() -> None:
    dark = _dark_tokens()
    for surface in ("--bg", "--surface", "--surface-soft", "--surface-muted"):
        assert _luminance(dark[surface]) < 0.05, surface
    assert _luminance(dark["--text"]) > 0.7


@pytest.mark.parametrize(
    ("foreground", "background", "minimum"),
    [
        ("--text", "--bg", 7.0),
        ("--text", "--surface", 7.0),
        ("--text", "--surface-muted", 7.0),
        ("--text-soft", "--surface-soft", 7.0),
        ("--muted", "--bg", 4.5),
        ("--muted", "--surface", 4.5),
        ("--muted", "--surface-muted", 4.5),
        ("--accent", "--surface", 4.5),
        ("--accent-text", "--surface", 4.5),
        ("--accent-text", "--accent-soft", 4.5),
        ("--slate", "--surface", 4.5),
        ("--primary", "--surface", 4.5),
    ],
)
def test_dark_palette_meets_wcag_contrast(foreground: str, background: str, minimum: float) -> None:
    dark = _dark_tokens()
    assert _contrast(dark[foreground], dark[background]) >= minimum


def test_dark_filled_buttons_keep_white_labels_readable() -> None:
    dark = _dark_tokens()
    assert _contrast("#ffffff", dark["--accent-strong"]) >= 4.5
    assert _contrast("#ffffff", dark["--accent-strong-hover"]) >= 4.5


@pytest.mark.parametrize("colour", ["#fbbf24", "#34d399", "#93c5fd", "#fca5a5", "#fdba74"])
def test_dark_status_and_alert_colours_are_readable(colour: str) -> None:
    dark = _dark_tokens()
    assert colour in _dark_section()
    assert _contrast(colour, dark["--surface"]) >= 4.5


@pytest.mark.parametrize(
    "selector",
    [
        # navegacion
        '[data-theme="dark"] .topbar',
        # tarjetas y login
        '[data-theme="dark"] .card',
        '[data-theme="dark"] .auth-card',
        '[data-theme="dark"] .modal-card',
        # formularios e inputs
        '[data-theme="dark"] input',
        '[data-theme="dark"] select',
        '[data-theme="dark"] textarea',
        # tablas
        '[data-theme="dark"] .board-table',
        '[data-theme="dark"] .board-table th',
        # dashboard
        '[data-theme="dark"] .kpi-card',
        '[data-theme="dark"] .quick-range',
        '[data-theme="dark"] .age-step .age-fill-track',
        # vista de detalle
        '[data-theme="dark"] .info-card-v2',
        '[data-theme="dark"] .original-request-box',
        '[data-theme="dark"] .timeline-item',
        '[data-theme="dark"] .timeline-text',
    ],
)
def test_dark_theme_overrides_hard_coded_light_surfaces(selector: str) -> None:
    assert selector in _dark_section()


def test_dark_rules_are_all_scoped_to_the_dark_theme() -> None:
    # Everything after the H3.3.7 marker is either the toggle itself or scoped to
    # [data-theme="dark"], so the light theme cannot be affected by accident.
    section = re.sub(r"/\*.*?\*/", "", _dark_section().split("*/", 1)[1], flags=re.S)
    selectors = [s.strip() for s in re.findall(r"([^{}]+)\{", section)]
    for group in selectors:
        for selector in (part.strip() for part in group.split(",")):
            assert selector.startswith('[data-theme="dark"]') or selector.startswith(
                ".theme-toggle"
            ), selector


# --------------------------------------------------------------------------- #
# No server interaction (AC-6)
# --------------------------------------------------------------------------- #


def test_theme_script_never_talks_to_the_server_or_uses_cookies() -> None:
    source = THEME_JS_PATH.read_text(encoding="utf-8")
    for forbidden in ("document.cookie", "fetch(", "XMLHttpRequest", "sendBeacon", "htmx"):
        assert forbidden not in source, forbidden


# --------------------------------------------------------------------------- #
# theme.js behaviour in Node (AC-4, AC-5, storage fallback)
# --------------------------------------------------------------------------- #

_NODE_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[1], "utf8");

function makeStorage(initial, mode) {
  const data = new Map(Object.entries(initial || {}));
  return {
    data,
    getItem(key) {
      if (mode === "get-throws") throw new Error("SecurityError");
      return data.has(key) ? data.get(key) : null;
    },
    setItem(key, value) {
      if (mode === "set-throws") throw new Error("QuotaExceededError");
      data.set(key, String(value));
    },
  };
}

function makeElement(attrs) {
  const attributes = Object.assign({}, attrs);
  const element = {
    getAttribute: (name) => (name in attributes ? attributes[name] : null),
    setAttribute: (name, value) => { attributes[name] = String(value); },
    closest(selector) {
      return selector === "[data-theme-toggle]" && "data-theme-toggle" in attributes
        ? element : null;
    },
  };
  return element;
}

function load(storageSpec) {
  const listeners = {};
  const root = makeElement({ "data-theme": "light" });
  const toggle = makeElement({ "data-theme-toggle": "", "aria-pressed": "false" });
  const other = makeElement({});
  const document = {
    documentElement: root,
    querySelectorAll: (selector) => (selector === "[data-theme-toggle]" ? [toggle] : []),
    addEventListener: (type, handler) => { (listeners[type] = listeners[type] || []).push(handler); },
  };
  const window = { document };
  if (storageSpec === "unavailable") {
    Object.defineProperty(window, "localStorage", {
      get() { throw new Error("SecurityError"); },
    });
  } else if (storageSpec !== "missing") {
    window.localStorage = storageSpec;
  }
  vm.runInNewContext(source, { window });
  const fire = (type, target) => (listeners[type] || []).forEach((h) => h({ target }));
  fire("DOMContentLoaded");
  return {
    theme: () => root.getAttribute("data-theme"),
    pressed: () => toggle.getAttribute("aria-pressed"),
    click: () => fire("click", toggle),
    clickElsewhere: () => fire("click", other),
    api: window.TpiTheme,
  };
}

const results = {};
const snap = (page) => ({ theme: page.theme(), pressed: page.pressed() });

results.no_preference = snap(load(makeStorage({})));
results.stored_dark = snap(load(makeStorage({ "tpi-theme": "dark" })));
results.stored_light = snap(load(makeStorage({ "tpi-theme": "light" })));
results.invalid_values = ["blue", "DARK", "", "null", " dark"].map(
  (value) => load(makeStorage({ "tpi-theme": value })).theme()
);

const persisted = makeStorage({});
const first = load(persisted);
first.click();
const afterToggle = Object.assign(snap(first), { stored: persisted.data.get("tpi-theme") });
const reloaded = snap(load(persisted));
first.click();
const afterSecondToggle = Object.assign(snap(first), { stored: persisted.data.get("tpi-theme") });
const reloadedLight = snap(load(persisted));
results.persistence = { afterToggle, reloaded, afterSecondToggle, reloadedLight };

const untouched = load(makeStorage({}));
untouched.clickElsewhere();
results.click_elsewhere = snap(untouched);

for (const spec of ["unavailable", "missing"]) {
  const page = load(spec);
  const initial = snap(page);
  page.click();
  results["storage_" + spec] = { initial, afterToggle: snap(page) };
}

const readThrows = load(makeStorage({ "tpi-theme": "dark" }, "get-throws"));
results.storage_get_throws = snap(readThrows);

const writeThrows = makeStorage({}, "set-throws");
const writeThrowsPage = load(writeThrows);
writeThrowsPage.click();
results.storage_set_throws = Object.assign(snap(writeThrowsPage), {
  storedKeys: writeThrows.data.size,
});

const sanitised = makeStorage({});
load(sanitised).api.store("<script>");
results.store_sanitises = sanitised.data.get("tpi-theme");

process.stdout.write(JSON.stringify(results));
"""


@pytest.fixture(scope="module")
def node_results() -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("Node.js is required in CI to exercise theme.js")
        pytest.skip("Node.js no esta instalado localmente; CI ejecuta estas pruebas")
    completed = subprocess.run(  # nosec B603 - fixed argv, no shell, repo file only
        [node, "-e", _NODE_HARNESS, str(THEME_JS_PATH)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    results: dict[str, Any] = json.loads(completed.stdout)
    return results


def test_without_preference_the_app_starts_light(node_results: dict[str, Any]) -> None:
    assert node_results["no_preference"] == {"theme": "light", "pressed": "false"}


def test_stored_preference_is_applied_on_load(node_results: dict[str, Any]) -> None:
    assert node_results["stored_dark"] == {"theme": "dark", "pressed": "true"}
    assert node_results["stored_light"] == {"theme": "light", "pressed": "false"}


def test_invalid_stored_values_fall_back_to_light(node_results: dict[str, Any]) -> None:
    assert node_results["invalid_values"] == ["light"] * 5


def test_toggle_persists_across_reloads(node_results: dict[str, Any]) -> None:
    persistence = node_results["persistence"]
    assert persistence["afterToggle"] == {"theme": "dark", "pressed": "true", "stored": "dark"}
    assert persistence["reloaded"] == {"theme": "dark", "pressed": "true"}
    assert persistence["afterSecondToggle"] == {
        "theme": "light",
        "pressed": "false",
        "stored": "light",
    }
    assert persistence["reloadedLight"] == {"theme": "light", "pressed": "false"}


def test_clicks_outside_the_toggle_do_not_change_the_theme(
    node_results: dict[str, Any],
) -> None:
    assert node_results["click_elsewhere"] == {"theme": "light", "pressed": "false"}


@pytest.mark.parametrize("spec", ["unavailable", "missing"])
def test_toggle_still_works_for_the_page_without_local_storage(
    node_results: dict[str, Any], spec: str
) -> None:
    result = node_results[f"storage_{spec}"]
    assert result["initial"] == {"theme": "light", "pressed": "false"}
    assert result["afterToggle"] == {"theme": "dark", "pressed": "true"}


def test_storage_errors_never_break_the_page(node_results: dict[str, Any]) -> None:
    assert node_results["storage_get_throws"] == {"theme": "light", "pressed": "false"}
    assert node_results["storage_set_throws"] == {
        "theme": "dark",
        "pressed": "true",
        "storedKeys": 0,
    }


def test_only_light_or_dark_is_ever_stored(node_results: dict[str, Any]) -> None:
    assert node_results["store_sanitises"] == "light"
