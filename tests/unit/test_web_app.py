"""Tests for the FastAPI web CRM UX layer."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.auth.models import AuthenticatedUser, AuthenticationResult
from app.components.ui import get_public_simulator_url
from app.config import Settings
from app.validators import mask_email, mask_phone, mask_rut
from app.web.main import create_web_app
from app.web.presentation import parse_lead_comments


class _FakeAuthProvider:
    def __init__(self, *, authenticated_role: str = "readonly") -> None:
        self.authenticated_role = authenticated_role

    def authenticate(self, username: str, password: str) -> AuthenticationResult:
        if username == "alvaro.local" and password == "AlvaroLocal!2026":
            return AuthenticationResult(
                status="authenticated",
                user=AuthenticatedUser(
                    subject="local-demo-alvaro",
                    username="alvaro.local",
                    display_name="Alvaro Local",
                    role=self.authenticated_role,
                ),
            )
        if username == "unavailable":
            return AuthenticationResult(status="unavailable")
        return AuthenticationResult(status="invalid")


class _FakeWebService:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self._full_detail = {
            "id_lead": "11111111-1111-1111-1111-111111111111",
            "nombre_completo": "Juan Perez",
            "rut": "12.345.678-5",
            "telefono": "+56 9 1234 5678",
            "afp": "Habitat",
            "saldo_afp": 1234567,
            "estado_lead": "pendiente",
            "comentarios": "Lead de prueba",
            "email": "juan@example.com",
            "fecha_nacimiento": date(1990, 1, 1),
            "genero": "Masculino",
            "estado_civil": "Soltero",
            "created_at": datetime(2026, 8, 21, 9, 45, tzinfo=UTC),
        }
        self.rows = (
            rows
            if rows is not None
            else [
                {
                    "id_lead": self._full_detail["id_lead"],
                    "nombre_completo": self._full_detail["nombre_completo"],
                    "rut": self._full_detail["rut"],
                    "telefono": self._full_detail["telefono"],
                    "afp": self._full_detail["afp"],
                    "saldo_afp": self._full_detail["saldo_afp"],
                    "estado_lead": self._full_detail["estado_lead"],
                    "comentarios": self._full_detail["comentarios"],
                    "created_at": self._full_detail["created_at"],
                    "email": self._full_detail["email"],
                    "fecha_nacimiento": self._full_detail["fecha_nacimiento"],
                    "genero": self._full_detail["genero"],
                    "estado_civil": self._full_detail["estado_civil"],
                }
            ]
        )
        self.last_board_kwargs: dict[str, object] = {}
        self.status_updates: list[tuple[str, str]] = []
        self.comment_appends: list[tuple[str, str, str]] = []

    def get_crm_bandeja(self, *args, **kwargs):
        self.last_board_kwargs = dict(kwargs)
        page = int(kwargs.get("page", 1))
        page_size = int(kwargs.get("page_size", 10))
        masked = bool(kwargs.get("masked", True))
        rows = [self._masked_row(row) if masked else dict(row) for row in self.rows]
        return {
            "solicitudes": rows,
            "total": len(rows),
            "page": page,
            "page_size": page_size,
            "total_pages": 1 if rows else 0,
        }

    def get_crm_estado_lead_options(self):
        return ["pendiente", "simulada", "en gestion"]

    def get_catalogo_afp(self):
        return [{"id": "afp-1", "nombre": "Habitat"}]

    def get_solicitud_detalle_masked(self, id_lead):
        if str(id_lead) != str(self._full_detail["id_lead"]):
            return None
        return self._masked_row(self._full_detail)

    def get_solicitud_detalle(self, id_lead):
        if str(id_lead) != str(self._full_detail["id_lead"]):
            return None
        return dict(self._full_detail)

    def update_lead_status(self, id_lead, estado_lead):
        if str(id_lead) != str(self._full_detail["id_lead"]):
            return False
        allowed = {"pendiente", "simulada", "en gestion", "cerrado", "aprobada"}
        if estado_lead not in allowed:
            raise ValueError("Estado de lead invalido")
        self._full_detail["estado_lead"] = estado_lead
        for row in self.rows:
            if str(row["id_lead"]) == str(id_lead):
                row["estado_lead"] = estado_lead
        self.status_updates.append((str(id_lead), estado_lead))
        return True

    def append_lead_comment(self, id_lead, comment_text, author):
        if str(id_lead) != str(self._full_detail["id_lead"]):
            return False
        fragment = f"[23/08/2026 10:15] {author}\n{comment_text}"
        previous = str(self._full_detail.get("comentarios") or "")
        self._full_detail["comentarios"] = f"{previous}\n\n{fragment}" if previous else fragment
        for row in self.rows:
            if str(row["id_lead"]) == str(id_lead):
                row["comentarios"] = self._full_detail["comentarios"]
        self.comment_appends.append((str(id_lead), comment_text, author))
        return True

    def delete_test_lead(self, id_lead):
        return type("Cleanup", (), {"status": "deleted", "message": "OK"})()

    def is_test_lead_cleanup_enabled(self):
        return True

    def get_solicitudes_por_rut(self, rut, masked=True):
        return []

    @staticmethod
    def _masked_row(row: dict[str, object]) -> dict[str, object]:
        masked = dict(row)
        masked["rut"] = mask_rut(str(masked["rut"]))
        masked["email"] = mask_email(str(masked["email"]))
        masked["telefono"] = mask_phone(str(masked["telefono"]))
        return masked


def _build_client(
    service: object | None = None,
    *,
    auth_provider: object | None = None,
    settings: Settings | None = None,
) -> TestClient:
    app = create_web_app()
    app.state.web_service = service or _FakeWebService()
    app.state.auth_provider = auth_provider or _FakeAuthProvider()
    app.state.settings = settings or Settings(
        APP_ENV="local",
        AUTH_ENABLED=True,
        AUTH_MODE="simple-dev",
        AUTH_USERS_JSON='{"users":[{"subject":"local-demo-alvaro","username":"alvaro.local","display_name":"Alvaro Local","role":"tester","password_hash":"$argon2id$v=19$m=65536,t=3,p=4$6NT/a6vLo9fBUi0s9oMZaQ$IyXdFj9Z2fhWtB49KKo4yeO/YhNaanInI55f9TjlF0o"}]}',
        WEB_MASK_PII=False,
    )
    app.state.web_simulator_url = get_public_simulator_url(app.state.settings)
    return TestClient(app)


def _login(
    client: TestClient, username: str = "alvaro.local", password: str = "AlvaroLocal!2026"
) -> None:
    response = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def test_web_app_initializes() -> None:
    app = create_web_app()
    assert app.title == "TPI Backoffice Web"


def test_login_and_leads_routes_render() -> None:
    client = _build_client()
    login = client.get("/login")
    assert login.status_code == 200
    assert "CRM Lite" in login.text

    invalid = client.post("/login", data={"username": "bad", "password": "bad"})
    assert invalid.status_code == 401
    assert "Credenciales invalidas" in invalid.text

    valid = client.post(
        "/login",
        data={"username": "alvaro.local", "password": "AlvaroLocal!2026"},
        follow_redirects=False,
    )
    assert valid.status_code == 303
    assert valid.headers["location"] == "/leads"

    leads = client.get("/leads")
    assert leads.status_code == 200
    assert "Leads" in leads.text
    assert "Buscar por nombre o RUT" in leads.text
    assert "Detalle del lead" not in leads.text
    assert "Contacto" not in leads.text

    detail = client.get("/leads/11111111-1111-1111-1111-111111111111")
    assert detail.status_code == 200
    assert "Juan Perez" in detail.text
    assert "Buscar por nombre o RUT" not in detail.text
    assert "Mostrando" not in detail.text
    assert "Abrir simulador" in detail.text
    assert "Juan Perez" in detail.text
    assert "12.345.678-5" in detail.text
    assert "juan@example.com" in detail.text
    assert "+56 9 1234 5678" in detail.text

    missing = client.get("/leads/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404
    assert "No encontramos el lead solicitado" in missing.text


def test_login_redirects_authenticated_users_to_board() -> None:
    client = _build_client()
    _login(client)

    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/leads"


def test_login_returns_service_unavailable_when_auth_provider_is_missing() -> None:
    client = _build_client()
    client.app.state.auth_provider = None

    response = client.post("/login", data={"username": "demo", "password": "demo"})
    assert response.status_code == 503
    assert "Autenticacion no disponible" in response.text


def test_protected_routes_redirect_without_session() -> None:
    client = _build_client()
    client.cookies.clear()

    leads = client.get("/leads", follow_redirects=False)
    assert leads.status_code == 307
    assert leads.headers["location"] == "/login"

    detail = client.get("/leads/11111111-1111-1111-1111-111111111111", follow_redirects=False)
    assert detail.status_code == 307
    assert detail.headers["location"] == "/login"


def test_logout_invalidates_session() -> None:
    client = _build_client()
    _login(client)

    logged = client.get("/leads")
    assert logged.status_code == 200

    logout = client.get("/logout", follow_redirects=False)
    assert logout.status_code == 303
    assert logout.headers["location"] == "/login"

    after_logout = client.get("/leads", follow_redirects=False)
    assert after_logout.status_code == 307
    assert after_logout.headers["location"] == "/login"


def test_readonly_users_do_not_see_write_actions() -> None:
    client = _build_client(auth_provider=_FakeAuthProvider(authenticated_role="readonly"))
    _login(client)

    detail = client.get("/leads/11111111-1111-1111-1111-111111111111")
    assert detail.status_code == 200
    assert "Eliminar lead de prueba" not in detail.text
    assert "Guardar estado" not in detail.text
    assert "Agregar nueva nota de seguimiento" not in detail.text


def test_detail_return_to_is_internal_and_preserves_context() -> None:
    client = _build_client()
    _login(client)

    response = client.get(
        "/leads/11111111-1111-1111-1111-111111111111",
        params={"return_to": "/leads?page=3&search=Perez"},
    )
    assert response.status_code == 200
    assert 'href="/leads?page=3&amp;search=Perez"' in response.text

    fallback = client.get(
        "/leads/11111111-1111-1111-1111-111111111111",
        params={"return_to": "https://evil.example.com"},
    )
    assert fallback.status_code == 200
    assert 'href="/leads"' in fallback.text


def test_detail_renders_simulator_link_from_central_configuration() -> None:
    client = _build_client(
        settings=Settings(
            APP_ENV="local",
            AUTH_ENABLED=True,
            AUTH_MODE="simple-dev",
            AUTH_USERS_JSON='{"users":[{"subject":"local-demo-alvaro","username":"alvaro.local","display_name":"Alvaro Local","role":"tester","password_hash":"$argon2id$v=19$m=65536,t=3,p=4$6NT/a6vLo9fBUi0s9oMZaQ$IyXdFj9Z2fhWtB49KKo4yeO/YhNaanInI55f9TjlF0o"}]}',
            WEB_MASK_PII=False,
            TPI_PUBLIC_SITE_URL="http://tpi.localhost:8080/",
        )
    )
    _login(client)

    detail = client.get("/leads/11111111-1111-1111-1111-111111111111")
    assert detail.status_code == 200
    assert 'href="http://tpi.localhost:8080/simulador.html"' in detail.text
    assert "data-simulator-link" in detail.text
    assert "btn-primary-simulator disabled" not in detail.text
    assert "Abrir simulador" in detail.text


def test_detail_disables_simulator_link_when_configuration_is_missing() -> None:
    client = _build_client(
        settings=Settings(
            APP_ENV="local",
            AUTH_ENABLED=True,
            AUTH_MODE="simple-dev",
            AUTH_USERS_JSON='{"users":[{"subject":"local-demo-alvaro","username":"alvaro.local","display_name":"Alvaro Local","role":"tester","password_hash":"$argon2id$v=19$m=65536,t=3,p=4$6NT/a6vLo9fBUi0s9oMZaQ$IyXdFj9Z2fhWtB49KKo4yeO/YhNaanInI55f9TjlF0o"}]}',
            WEB_MASK_PII=False,
        )
    )
    _login(client)

    detail = client.get("/leads/11111111-1111-1111-1111-111111111111")
    assert detail.status_code == 200
    assert '<span class="btn-primary-simulator disabled">' in detail.text
    assert "data-simulator-link" not in detail.text


def test_web_status_update_and_comment_append_are_protected_and_incremental() -> None:
    service = _FakeWebService()
    client = _build_client(service, auth_provider=_FakeAuthProvider(authenticated_role="tester"))
    _login(client)

    detail = client.get("/leads/11111111-1111-1111-1111-111111111111")
    csrf = _extract_csrf(detail.text)

    status_response = client.post(
        "/leads/11111111-1111-1111-1111-111111111111/status",
        data={"csrf_token": csrf, "estado_lead": "simulada", "return_to": "/leads?page=2"},
        follow_redirects=False,
    )
    assert status_response.status_code == 303
    assert (
        "/leads/11111111-1111-1111-1111-111111111111?return_to="
        in status_response.headers["location"]
    )
    assert service.status_updates[-1][1] == "simulada"

    refreshed = client.get("/leads/11111111-1111-1111-1111-111111111111")
    csrf = _extract_csrf(refreshed.text)
    comment_response = client.post(
        "/leads/11111111-1111-1111-1111-111111111111/comments",
        data={
            "csrf_token": csrf,
            "new_comment": "Seguimiento agregado desde test",
            "return_to": "/leads?page=2",
        },
        follow_redirects=False,
    )
    assert comment_response.status_code == 303
    assert service.comment_appends[-1][1] == "Seguimiento agregado desde test"

    final_detail = client.get("/leads/11111111-1111-1111-1111-111111111111")
    assert "Simulada" in final_detail.text or "simulada" in final_detail.text
    assert "Seguimiento agregado desde test" in final_detail.text
    assert "Lead de prueba" in final_detail.text
    assert "Solicitud Original" in final_detail.text
    assert "Seguimiento y Notas Internas" in final_detail.text


def test_comment_parser_separates_original_and_followups_safely() -> None:
    empty = parse_lead_comments("")
    assert empty.original_request == ""
    assert empty.notes == []

    original_only = parse_lead_comments("Quiero revisar mi pensión.")
    assert original_only.original_request == "Quiero revisar mi pensión."
    assert original_only.notes == []

    one_note = parse_lead_comments(
        "Quiero revisar mi pensión.\n\n[23/08/2026 22:32] Alvaro Local\nCliente contactado."
    )
    assert one_note.original_request == "Quiero revisar mi pensión."
    assert len(one_note.notes) == 1
    assert one_note.notes[0].timestamp == "23/08/2026 22:32"
    assert one_note.notes[0].author == "Alvaro Local"
    assert one_note.notes[0].text == "Cliente contactado."

    many_notes = parse_lead_comments(
        "Solicitud original.\n\n"
        "[23/08/2026 22:32] Alvaro Local\nCliente contactado.\n\n"
        "[24/08/2026 09:14] Carolina Silva\nNueva nota de seguimiento."
    )
    assert many_notes.original_request == "Solicitud original."
    assert [note.author for note in many_notes.notes] == ["Alvaro Local", "Carolina Silva"]

    multiline_note = parse_lead_comments(
        "Solicitud original.\n\n[23/08/2026 22:32] Alvaro Local\nLinea 1\nLinea 2"
    )
    assert multiline_note.notes[0].text == "Linea 1\nLinea 2"

    malformed = parse_lead_comments("Solicitud original.\n\n[texto no valido]")
    assert malformed.original_request == "Solicitud original.\n\n[texto no valido]"
    assert malformed.notes == []
    assert malformed.is_fallback is True

    brackets = parse_lead_comments("Solicitud original con [corchetes] sin marcador.")
    assert brackets.original_request == "Solicitud original con [corchetes] sin marcador."
    assert brackets.notes == []


def test_web_status_update_rejects_invalid_csrf_and_readonly_role() -> None:
    service = _FakeWebService()
    readonly_client = _build_client(
        service, auth_provider=_FakeAuthProvider(authenticated_role="readonly")
    )
    _login(readonly_client)

    denied = readonly_client.post(
        "/leads/11111111-1111-1111-1111-111111111111/status",
        data={"csrf_token": "bad", "estado_lead": "simulada"},
        follow_redirects=False,
    )
    assert denied.status_code == 403
    assert "Esta accion no esta disponible para este usuario" in denied.text

    authorized_client = _build_client(
        service, auth_provider=_FakeAuthProvider(authenticated_role="tester")
    )
    _login(authorized_client)
    detail = authorized_client.get("/leads/11111111-1111-1111-1111-111111111111")
    csrf = _extract_csrf(detail.text)

    invalid = authorized_client.post(
        "/leads/11111111-1111-1111-1111-111111111111/status",
        data={"csrf_token": csrf, "estado_lead": "estado-inventado"},
        follow_redirects=False,
    )
    assert invalid.status_code == 400
    assert "No fue posible actualizar el estado" in invalid.text

    invalid_comment = authorized_client.post(
        "/leads/11111111-1111-1111-1111-111111111111/comments",
        data={"csrf_token": csrf, "new_comment": "   "},
        follow_redirects=False,
    )
    assert invalid_comment.status_code == 400
    assert "Debes ingresar una nota de seguimiento" in invalid_comment.text


def test_detail_page_does_not_render_board_controls() -> None:
    client = _build_client(auth_provider=_FakeAuthProvider(authenticated_role="tester"))
    _login(client)

    detail = client.get("/leads/11111111-1111-1111-1111-111111111111")
    assert detail.status_code == 200
    assert "Solicitud Original" in detail.text
    assert "Seguimiento y Notas Internas" in detail.text
    assert "Buscar por nombre o RUT" not in detail.text
    assert "Mostrando" not in detail.text
    assert "Guardar estado" in detail.text
    assert "Agregar nueva nota de seguimiento" in detail.text


def test_web_filters_and_pagination_preserve_query_params() -> None:
    service = _FakeWebService()
    client = _build_client(service)
    _login(client)

    response = client.get(
        "/leads",
        params={
            "search": "Perez",
            "afp_id": "afp-1",
            "estado_lead": "pendiente",
            "date_from": "2026-08-21",
            "date_to": "2026-08-21",
            "sort_by": "nombre_completo",
            "sort_direction": "asc",
            "page": "2",
        },
    )
    assert response.status_code == 200
    assert service.last_board_kwargs["search"] == "Perez"
    assert service.last_board_kwargs["afp_id"] == "afp-1"
    assert service.last_board_kwargs["estado_lead"] == "pendiente"
    assert service.last_board_kwargs["date_from"] == date(2026, 8, 21)
    assert service.last_board_kwargs["date_to"] == date(2026, 8, 21)
    assert service.last_board_kwargs["sort_by"] == "nombre_completo"
    assert service.last_board_kwargs["sort_direction"] == "asc"
    assert (
        'href="/leads?search=Perez&amp;afp_id=afp-1&amp;estado_lead=pendiente'
        "&amp;date_from=2026-08-21&amp;date_to=2026-08-21&amp;sort_by=nombre_completo"
        '&amp;sort_direction=asc&amp;page=1"'
    ) in response.text


def test_web_board_empty_states_are_distinct() -> None:
    empty_client = _build_client(_FakeWebService(rows=[]))
    _login(empty_client)

    no_filters = empty_client.get("/leads")
    assert no_filters.status_code == 200
    assert "no existen solicitudes en el sistema" in no_filters.text

    with_filters = empty_client.get("/leads", params={"search": "sin coincidencias"})
    assert with_filters.status_code == 200
    assert "No encontramos leads con estos filtros" in with_filters.text


def test_web_masking_can_be_disabled_for_non_production_local_demo() -> None:
    client = _build_client(
        settings=Settings(
            APP_ENV="local",
            AUTH_ENABLED=True,
            AUTH_MODE="simple-dev",
            AUTH_USERS_JSON='{"users":[{"subject":"local-demo-alvaro","username":"alvaro.local","display_name":"Alvaro Local","role":"tester","password_hash":"$argon2id$v=19$m=65536,t=3,p=4$6NT/a6vLo9fBUi0s9oMZaQ$IyXdFj9Z2fhWtB49KKo4yeO/YhNaanInI55f9TjlF0o"}]}',
            WEB_MASK_PII=False,
        )
    )
    _login(client)

    detail = client.get("/leads/11111111-1111-1111-1111-111111111111")
    assert "12.345.678-5" in detail.text
    assert mask_rut("12.345.678-5") not in detail.text
    assert "juan@example.com" in detail.text
    assert mask_email("juan@example.com") not in detail.text
    assert "+56 9 1234 5678" in detail.text
    assert mask_phone("+56 9 1234 5678") not in detail.text


def test_web_masking_stays_enabled_in_production_even_if_disabled() -> None:
    client = _build_client(
        settings=Settings(
            APP_ENV="production",
            AUTH_ENABLED=True,
            AUTH_MODE="simple-dev",
            AUTH_USERS_JSON='{"users":[{"subject":"local-demo-alvaro","username":"alvaro.local","display_name":"Alvaro Local","role":"tester","password_hash":"$argon2id$v=19$m=65536,t=3,p=4$6NT/a6vLo9fBUi0s9oMZaQ$IyXdFj9Z2fhWtB49KKo4yeO/YhNaanInI55f9TjlF0o"}]}',
            WEB_MASK_PII=False,
        )
    )
    _login(client)

    detail = client.get("/leads/11111111-1111-1111-1111-111111111111")
    assert mask_rut("12.345.678-5") in detail.text
    assert mask_email("juan@example.com") in detail.text
    assert mask_phone("+56 9 1234 5678") in detail.text


def test_templates_and_static_assets_exist() -> None:
    for relative in (
        Path("app/web/templates/base.html"),
        Path("app/web/templates/login.html"),
        Path("app/web/templates/leads.html"),
        Path("app/web/templates/leads_board.html"),
        Path("app/web/templates/lead_detail.html"),
        Path("app/web/templates/lead_detail_panel.html"),
        Path("app/web/static/css/app.css"),
        Path("app/web/static/js/app.js"),
    ):
        assert relative.exists(), f"Missing web asset: {relative}"


def test_static_assets_can_be_served() -> None:
    client = _build_client()
    response = client.get("/static/css/app.css")
    assert response.status_code == 200
    assert "CRM Lite" not in response.text
