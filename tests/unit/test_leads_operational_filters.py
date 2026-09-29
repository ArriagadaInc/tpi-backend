"""Unit tests for the operational filters the dashboard alerts link to.

The "Ver detalle" links are real: ``/leads?sin_asignar=1`` and
``/leads?estancado=1`` must reach the listing as server-side filters, survive a
filter update, be cleared by "Limpiar", and keep the existing PII masking and
RBAC untouched.
"""

from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient

from app.auth.models import AuthenticatedUser, AuthenticationResult
from app.config import Settings
from app.repositories.solicitud_repository import SolicitudRepository
from app.web.main import create_web_app

ADVISOR_ID = "44444444-4444-4444-4444-444444444441"


class _FakeAuthProvider:
    def authenticate(self, username: str, password: str) -> AuthenticationResult:
        roles = {"ceo.local": "ceo", "advisor.local": "advisor"}
        role = roles.get(username)
        if role is None:
            return AuthenticationResult(status="invalid")
        return AuthenticationResult(
            status="authenticated",
            user=AuthenticatedUser(
                subject=f"{role}-subject",
                username=username,
                display_name=f"{role.title()} Demo",
                role=role,  # type: ignore[arg-type]
            ),
        )


class _SpyService:
    def __init__(self) -> None:
        self.board_kwargs: dict[str, object] = {}

    def can_view_full_pii(self, user) -> bool:
        return user.role in ("ceo", "cto")

    def get_crm_bandeja(self, **kwargs):
        self.board_kwargs = dict(kwargs)
        return {"solicitudes": [], "total": 0, "page": 1, "page_size": 10, "total_pages": 0}

    def get_catalogo_afp(self):
        return [{"id": "afp-1", "nombre": "Habitat"}]

    def get_crm_estado_lead_options(self):
        return ["nuevo", "cerrado"]


def _client(service: _SpyService) -> TestClient:
    app = create_web_app()
    app.state.web_service = service
    app.state.auth_provider = _FakeAuthProvider()
    app.state.settings = Settings(APP_ENV="local", AUTH_ENABLED=True, AUTH_MODE="simple-dev")
    return TestClient(app)


def _login(client: TestClient, username: str = "ceo.local") -> None:
    response = client.post(
        "/login", data={"username": username, "password": "x"}, follow_redirects=False
    )
    assert response.status_code == 303


# --------------------------------------------------------------------------- #
# Query parameters reach the service
# --------------------------------------------------------------------------- #


def test_sin_asignar_query_param_reaches_the_service() -> None:
    service = _SpyService()
    client = _client(service)
    _login(client)
    assert client.get("/leads?sin_asignar=1").status_code == 200
    assert service.board_kwargs["sin_asignar"] is True
    assert service.board_kwargs["estancado"] is False


def test_estancado_query_param_reaches_the_service() -> None:
    service = _SpyService()
    client = _client(service)
    _login(client)
    assert client.get("/leads?estancado=1").status_code == 200
    assert service.board_kwargs["estancado"] is True


def test_dimension_filters_from_the_dashboard_reach_the_service() -> None:
    service = _SpyService()
    client = _client(service)
    _login(client)
    client.get(f"/leads?asesor={ADVISOR_ID}&origen=formulario_web&fuente=organico&sin_asignar=1")
    assert service.board_kwargs["asesor_id"] == UUID(ADVISOR_ID)
    assert service.board_kwargs["origen_lead"] == "formulario_web"
    assert service.board_kwargs["fuente_actual"] == "organico"


def test_unparseable_advisor_is_ignored_instead_of_failing() -> None:
    service = _SpyService()
    client = _client(service)
    _login(client)
    assert client.get("/leads?asesor=not-a-uuid").status_code == 200
    assert service.board_kwargs["asesor_id"] is None


def test_non_truthy_flag_values_do_not_activate_the_filter() -> None:
    service = _SpyService()
    client = _client(service)
    _login(client)
    client.get("/leads?sin_asignar=0&estancado=no")
    assert service.board_kwargs["sin_asignar"] is False
    assert service.board_kwargs["estancado"] is False


# --------------------------------------------------------------------------- #
# The listing UI keeps the filters and can clear them
# --------------------------------------------------------------------------- #


def test_active_operational_filters_are_visible_and_preserved() -> None:
    client = _client(_SpyService())
    _login(client)
    body = client.get("/leads?sin_asignar=1").text
    assert "Solo leads sin asignar" in body
    assert '<input type="hidden" name="sin_asignar" value="1">' in body


def test_estancado_filter_is_visible_and_preserved() -> None:
    client = _client(_SpyService())
    _login(client)
    body = client.get("/leads?estancado=1").text
    assert "Solo leads estancados" in body
    assert '<input type="hidden" name="estancado" value="1">' in body


def test_clear_link_drops_every_filter() -> None:
    client = _client(_SpyService())
    _login(client)
    body = client.get("/leads?estancado=1&search=juan").text
    assert '<a class="secondary" href="/leads">Limpiar</a>' in body


def test_empty_result_message_acknowledges_the_operational_filter() -> None:
    client = _client(_SpyService())
    _login(client)
    body = client.get("/leads?sin_asignar=1").text
    assert "No encontramos leads con estos filtros" in body


# --------------------------------------------------------------------------- #
# The SQL predicates are the shared ones (no divergent duplicate)
# --------------------------------------------------------------------------- #


def test_listing_uses_the_shared_unassigned_predicate() -> None:
    from app.repositories.lead_activity_sql import sin_asignar_predicate

    where, params = SolicitudRepository._build_crm_query_filters(sin_asignar=True)
    assert sin_asignar_predicate("l").strip() in where
    assert params == ["activa"]


def test_listing_uses_the_shared_stale_predicate_with_the_default_threshold() -> None:
    from app.models.executive_dashboard import estancamiento_dias_default
    from app.repositories.lead_activity_sql import NOTE_TS_PATTERN, estancado_predicate

    where, params = SolicitudRepository._build_crm_query_filters(estancado=True)
    assert estancado_predicate("l").strip() in where
    assert params == [NOTE_TS_PATTERN, estancamiento_dias_default()]


def test_stale_threshold_is_configurable_from_a_single_place() -> None:
    from app.repositories.lead_activity_sql import NOTE_TS_PATTERN

    _, params = SolicitudRepository._build_crm_query_filters(estancado=True, estancamiento_dias=9)
    assert params == [NOTE_TS_PATTERN, 9]


def test_operational_filters_combine_with_the_existing_ones() -> None:
    where, params = SolicitudRepository._build_crm_query_filters(
        estado_lead="nuevo",
        sin_asignar=True,
        estancado=True,
        origen_lead="formulario_web",
    )
    assert where.startswith("WHERE ")
    assert where.count(" AND ") >= 3
    assert "activa" in params
    assert "formulario_web" in params


# --------------------------------------------------------------------------- #
# Existing RBAC / PII behaviour is untouched
# --------------------------------------------------------------------------- #


def test_anonymous_user_is_still_redirected_to_login() -> None:
    client = _client(_SpyService())
    response = client.get("/leads?sin_asignar=1", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/login"


def test_masking_decision_is_unchanged_by_the_new_filters() -> None:
    service = _SpyService()
    client = _client(service)
    _login(client, "advisor.local")
    client.get("/leads?estancado=1")
    assert service.board_kwargs["masked"] is True
