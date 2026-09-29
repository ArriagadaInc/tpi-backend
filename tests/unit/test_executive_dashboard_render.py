"""Render tests for the productive Executive Dashboard page (H3.3.4, Parte B).

These exercise the real route, the real template and the real CSS classes with a
service double, covering: navigation and RBAC, the two visible scopes, KPIs and
alerts, charts (including zero and single-observation series), funnel
availability, the advisor table, empty/partial/global error states, filter
persistence and the absence of any lead or advisor PII in the served HTML.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.auth.models import AuthenticatedUser, AuthenticationResult
from app.config import Settings
from app.models.executive_dashboard import (
    AlertTarget,
    AntiguedadBucket,
    AsesorRow,
    CurrentSnapshot,
    DashboardFilters,
    DistribucionBucket,
    EstadoAsesorCell,
    EstadoBucket,
    EvolucionPoint,
    ExecutiveDashboard,
    Funnel,
    FunnelStep,
    PeriodActivity,
    TiempoMetric,
)
from app.services.executive_dashboard_service import ExecutiveDashboardService
from app.web.main import create_web_app

TOTAL = 1842
ACTIVA = 1041
ADVISOR_NAME = "María Contreras Bravo"
ADVISOR_ID = "44444444-4444-4444-4444-444444444441"
AFP_ID = "55555555-5555-5555-5555-555555555551"


class _FakeAuthProvider:
    def authenticate(self, username: str, password: str) -> AuthenticationResult:
        roles = {
            "ceo.local": "ceo",
            "cto.local": "cto",
            "advisor.local": "advisor",
            "admin.local": "admin",
        }
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


def _estado(estado: str, label: str, n: int) -> EstadoBucket:
    return EstadoBucket(
        estado=estado, label=label, n=n, denominador=TOTAL, percentage=round(n / TOTAL, 4)
    )


def _edad(bucket: str, n: int) -> AntiguedadBucket:
    return AntiguedadBucket(bucket=bucket, n=n, denominador=ACTIVA, percentage=round(n / ACTIVA, 4))


def _cat(nombre: str, n: int) -> DistribucionBucket:
    return DistribucionBucket(
        categoria=nombre, n=n, denominador=TOTAL, percentage=round(n / TOTAL, 4)
    )


def _full_dashboard(
    *,
    failed: tuple[str, ...] = (),
    evolucion: list[EvolucionPoint] | None = None,
    funnel: Funnel | None = None,
) -> ExecutiveDashboard:
    filters = DashboardFilters.from_raw(
        fecha_desde="2026-08-19", fecha_hasta="2026-09-17", granularidad="diaria"
    )
    snapshot = CurrentSnapshot(
        total_leads=TOTAL,
        cartera_activa=ACTIVA,
        sin_asignar=37,
        estancados=58,
        casos_por_estado=[
            _estado("cerrado", "Cerrado", 600),
            _estado("contactado", "Contactado", 280),
            _estado("estado_legacy_desconocido", "estado_legacy_desconocido", 12),
        ],
        antiguedad=[_edad("0-2", 210), _edad("+30", 81)],
        estancados_por_antiguedad=[_edad("+30", 58)],
        cartera_por_asesor=[
            AsesorRow(ADVISOR_ID, ADVISOR_NAME, 312, 198, 12, 300, 0.175, 180, 1.1),
            AsesorRow(None, "Sin asesor", 37, 37, 6, 0, None, 0, None),
        ],
        casos_por_estado_y_asesor=[
            EstadoAsesorCell(ADVISOR_ID, ADVISOR_NAME, "contactado", "Contactado", 96)
        ],
        distribucion_afp=[_cat("Habitat", 512)],
        distribucion_origen=[_cat("formulario_web", 760)],
        distribucion_fuente=[_cat("campana_digital", 690)],
    )
    period = PeriodActivity(
        leads_ingresados=214,
        evolucion=(
            evolucion
            if evolucion is not None
            else [EvolucionPoint(f"2026-09-{day:02d}", day) for day in range(1, 15)]
        ),
        funnel=(
            funnel
            if funnel is not None
            else Funnel(
                scope="period_activity",
                cutover="2026-09-05",
                cobertura_completa=True,
                excluidos_pre_cutover=0,
                denominador=214,
                steps=[FunnelStep("nuevo", "contactado", "Nuevo", "Contactado", 162, 214, 0.757)],
                periodo_activo=True,
            )
        ),
        tiempo_asignacion=TiempoMetric(n=1805, media_dias=0.21),
        tiempo_primera_gestion=TiempoMetric(n=190, media_dias=1.2),
    )
    return ExecutiveDashboard(
        filters=filters,
        current_snapshot=snapshot,
        period_activity=period,
        alerts=[
            AlertTarget("sin_asignar", 37, {"sin_asignar": True}),
            AlertTarget("estancados", 58, {"estancado": True}),
        ],
        failed_sections=failed,
    )


def _empty_dashboard() -> ExecutiveDashboard:
    filters = DashboardFilters.from_raw(fecha_desde="2026-09-01", fecha_hasta="2026-09-17")
    return ExecutiveDashboard(
        filters=filters,
        current_snapshot=CurrentSnapshot(),
        period_activity=PeriodActivity(
            funnel=Funnel(
                scope="period_activity",
                cutover="2026-09-05",
                cobertura_completa=True,
                excluidos_pre_cutover=0,
                denominador=0,
                steps=[],
                periodo_activo=True,
            )
        ),
        alerts=[
            AlertTarget("sin_asignar", 0, {"sin_asignar": True}),
            AlertTarget("estancados", 0, {"estancado": True}),
        ],
    )


class _StubService(ExecutiveDashboardService):
    def __init__(
        self, builder=None, *, raise_global: bool = False, cutover: str | None = "2026-09-05"
    ):
        settings_kwargs = {"APP_ENV": "testing"}
        if cutover is not None:
            settings_kwargs["LEAD_STATE_HISTORY_CUTOVER"] = cutover
        super().__init__(repository=object(), settings=Settings(**settings_kwargs))  # type: ignore[arg-type]
        self._builder = builder or _full_dashboard
        self._raise = raise_global
        self.calls = 0

    def build_executive_dashboard(self, filters: DashboardFilters) -> ExecutiveDashboard:
        self.calls += 1
        if self._raise:
            raise RuntimeError("repository unavailable")
        return self._builder()

    def get_filter_options(self) -> dict[str, list[object]]:
        return {
            "estados": [{"value": "nuevo", "label": "Nuevo"}],
            "asesores": [{"value": ADVISOR_ID, "label": ADVISOR_NAME}],
            "afps": [{"value": AFP_ID, "label": "Habitat"}],
            "origenes": ["formulario_web"],
            "fuentes": ["campana_digital"],
        }


def _client(service: ExecutiveDashboardService | None = None) -> TestClient:
    app = create_web_app()
    app.state.executive_dashboard_service = service or _StubService()
    app.state.auth_provider = _FakeAuthProvider()
    app.state.settings = Settings(APP_ENV="local", AUTH_ENABLED=True, AUTH_MODE="simple-dev")
    return TestClient(app)


def _login(client: TestClient, username: str) -> None:
    response = client.post(
        "/login", data={"username": username, "password": "x"}, follow_redirects=False
    )
    assert response.status_code == 303


def _page(username: str = "ceo.local", query: str = "", service=None) -> str:
    client = _client(service)
    _login(client, username)
    response = client.get(f"/dashboard{query}")
    assert response.status_code == 200, response.status_code
    return response.text


# --------------------------------------------------------------------------- #
# Navigation and RBAC
# --------------------------------------------------------------------------- #


def test_nav_link_is_visible_for_ceo() -> None:
    client = _client()
    _login(client, "ceo.local")
    body = client.get("/dashboard").text
    assert 'href="/dashboard"' in body
    assert "Dashboard Ejecutivo" in body


def test_nav_link_is_visible_for_cto() -> None:
    client = _client()
    _login(client, "cto.local")
    body = client.get("/dashboard").text
    assert 'href="/dashboard"' in body


def test_nav_link_is_hidden_for_other_roles() -> None:
    client = _client()
    _login(client, "advisor.local")
    body = client.get("/leads").text
    assert 'href="/leads"' in body
    assert 'href="/dashboard"' not in body


def test_hiding_the_link_is_not_the_access_control() -> None:
    """The link is absent for an advisor and the route still returns a real 403."""
    client = _client()
    _login(client, "advisor.local")
    assert 'href="/dashboard"' not in client.get("/leads").text
    assert client.get("/dashboard").status_code == 403


def test_rejected_response_carries_no_dashboard_structure_or_data() -> None:
    service = _StubService()
    client = _client(service)
    _login(client, "admin.local")
    response = client.get("/dashboard")
    assert response.status_code == 403
    assert service.calls == 0
    for marker in ("kpi-grid", "bar-list", "age-ladder", "timeseries-svg", "asesor-table", "1.842"):
        assert marker not in response.text


def test_anonymous_receives_403_without_dashboard_markup() -> None:
    response = _client().get("/dashboard")
    assert response.status_code == 403
    assert "kpi-grid" not in response.text


# --------------------------------------------------------------------------- #
# Normal render: scopes, KPIs, alerts
# --------------------------------------------------------------------------- #


def test_normal_render_shows_both_scopes_explicitly() -> None:
    body = _page()
    assert "current_snapshot" in body
    assert "period_activity" in body
    assert "Las métricas de cartera representan la situación actual" in body
    assert "período seleccionado se aplica a ingresos" in body


def test_kpi_cards_render_every_headline_metric() -> None:
    body = _page()
    assert "Total de leads" in body
    assert "1.842" in body
    assert "Ingresados en el período" in body
    assert "214" in body
    assert "Cartera activa" in body
    assert "1.041" in body
    assert "Leads sin asignar" in body
    assert "fecha_ingreso" in body
    assert "created_at" in body


def test_alerts_render_with_real_listing_links() -> None:
    body = _page()
    assert "37 leads sin asignar" in body
    assert "58 leads estancados" in body
    assert "/leads?sin_asignar=1" in body
    assert "/leads?estancado=1" in body


def test_alert_links_carry_the_same_dimension_filters_as_the_dashboard() -> None:
    body = _page(query="?estado=nuevo&origen=formulario_web&sin_asignar=1")
    assert "estado_lead=nuevo" in body
    assert "origen=formulario_web" in body
    # The period never travels to the listing: alerts belong to the snapshot scope.
    assert "date_from" not in body


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #


def test_charts_are_server_rendered_without_javascript_or_cdn() -> None:
    body = _page()
    assert "<svg" in body
    assert "<canvas" not in body
    assert "cdn" not in body.lower().replace("cdn_", "")
    assert "chart.js" not in body.lower()
    # No dataset is embedded for a client-side chart library.
    assert "JSON.parse" not in body
    assert "const data" not in body


def test_every_chart_has_a_title_a_summary_and_an_accessible_table() -> None:
    body = _page()
    assert "Evolución de ingresos" in body
    assert "Casos por estado" in body
    assert "Antigüedad de la cartera activa" in body
    assert "Distribución por categorías" in body
    assert body.count("Ver como tabla") >= 4
    assert "<caption>" in body
    assert 'scope="col"' in body
    assert "<title " in body and "<desc " in body


def test_percentages_always_show_n_and_the_denominator() -> None:
    body = _page()
    assert "600 · 32,6% (600/1.842)" in body


def test_state_bars_use_a_reproducible_order_and_escape_unknown_values() -> None:
    body = _page()
    assert body.index("Cerrado") < body.index("Contactado")
    assert "estado_legacy_desconocido" in body


def test_state_bars_link_to_a_reproducible_filtered_view() -> None:
    body = _page(query="?fecha_desde=2026-08-19&fecha_hasta=2026-09-17")
    assert "/dashboard?fecha_desde=2026-08-19&amp;fecha_hasta=2026-09-17&amp;estado=cerrado" in body
    # The link is a real anchor, not a decorative element with a click handler.
    assert 'class="bar-label" href="/dashboard?' in body


def test_category_bars_are_not_decorative_links() -> None:
    """AFP/origen/fuente buckets have no reproducible filter value, so no link."""
    body = _page()
    assert 'href="#"' not in body


def test_age_ladder_marks_the_priority_bucket_with_text() -> None:
    body = _page()
    assert "Más de 30 días" in body
    assert "Prioridad alta de revisión" in body


def test_mvp_categories_only_no_gender_or_marital_status() -> None:
    body = _page().lower()
    for forbidden in ("género", "genero", "estado civil", "estado_civil"):
        assert forbidden not in body
    for expected in ("afp", "origen del lead", "fuente actual"):
        assert expected in body


def test_timeseries_with_a_single_point_renders_a_marker_and_no_polyline() -> None:
    service = _StubService(lambda: _full_dashboard(evolucion=[EvolucionPoint("2026-09-17", 7)]))
    body = _page(service=service)
    assert "timeseries-dot" in body
    assert "timeseries-line" not in body
    assert "Una sola observación" in body


def test_timeseries_with_all_zero_values_renders_without_dividing_by_zero() -> None:
    points = [EvolucionPoint(f"2026-09-0{i}", 0) for i in range(1, 4)]
    body = _page(service=_StubService(lambda: _full_dashboard(evolucion=points)))
    assert "timeseries-svg" in body
    assert "nan" not in body.lower()


def test_timeseries_without_observations_shows_the_empty_state() -> None:
    body = _page(service=_StubService(lambda: _full_dashboard(evolucion=[])))
    assert "Sin ingresos en el período" in body
    assert "timeseries-svg" not in body


# --------------------------------------------------------------------------- #
# Funnel
# --------------------------------------------------------------------------- #


def test_funnel_renders_rates_with_n_and_base_when_coverage_is_complete() -> None:
    body = _page()
    assert "Funnel y tasas observables" in body
    assert "Nuevo → Contactado" in body
    assert "162 · 75,7% (162/214)" in body


def test_funnel_is_unavailable_without_cutover_and_explains_why() -> None:
    funnel = Funnel(
        scope="period_activity",
        cutover=None,
        cobertura_completa=False,
        excluidos_pre_cutover=0,
        denominador=0,
        steps=[],
        periodo_activo=True,
    )
    body = _page(service=_StubService(lambda: _full_dashboard(funnel=funnel), cutover=None))
    assert "No disponible con cobertura suficiente" in body
    assert "corte de la migración 008" in body
    assert "75,7%" not in body


def test_funnel_is_unavailable_when_coverage_is_partial() -> None:
    funnel = Funnel(
        scope="period_activity",
        cutover="2026-09-05",
        cobertura_completa=True,
        excluidos_pre_cutover=412,
        denominador=214,
        steps=[FunnelStep("nuevo", "contactado", "Nuevo", "Contactado", 162, 214, 0.757)],
        periodo_activo=True,
    )
    body = _page(service=_StubService(lambda: _full_dashboard(funnel=funnel)))
    assert "No disponible con cobertura suficiente" in body
    assert "162 · 75,7%" not in body


def test_coverage_notice_is_always_visible() -> None:
    assert "Cobertura de datos" in _page()


# --------------------------------------------------------------------------- #
# Advisor summary
# --------------------------------------------------------------------------- #


def test_advisor_table_shows_only_the_allowed_columns() -> None:
    body = _page()
    assert "Resumen por asesor" in body
    for header in (
        "Cartera total",
        "Cartera activa",
        "Estancados",
        "Tiempo a asignación",
        "Tiempo a primera gestión",
    ):
        assert header in body
    assert ADVISOR_NAME in body
    assert "Sin asesor" in body


def test_advisor_without_first_management_shows_nd_not_zero() -> None:
    body = _page()
    assert "N/D" in body


def test_served_html_contains_no_pii_value_of_any_kind() -> None:
    """The page may *say* it excludes PII; it must never contain a PII value."""
    body = _page()
    # Scope the scan to the rendered dashboard; the <head> carries the pre-existing
    # htmx CDN tag, which is outside this task and is not a PII surface.
    main = re.search(r"<main\b.*?</main>", body, flags=re.S)
    assert main is not None
    rendered = main.group(0)
    assert re.search(r"\d{1,2}\.\d{3}\.\d{3}-[0-9kK]", rendered) is None, "RUT-like value"
    assert re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", rendered) is None, "e-mail-like value"
    assert re.search(r"\+?56\s?9\s?\d{4}\s?\d{4}", rendered) is None, "phone-like value"
    for field in ("nombre_completo", "id_persona", "fecha_nacimiento", "saldo_afp"):
        assert field not in rendered


def test_no_aggregate_data_is_embedded_in_scripts_or_comments() -> None:
    body = _page()
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", body, flags=re.S)
    for script in scripts:
        assert "1.842" not in script
        assert "1041" not in script
    for comment in re.findall(r"<!--(.*?)-->", body, flags=re.S):
        assert "1.842" not in comment
        assert "214" not in comment


def test_state_by_advisor_matrix_is_available_without_extra_columns() -> None:
    body = _page()
    assert "Ver casos por estado y asesor" in body


# --------------------------------------------------------------------------- #
# Empty, partial and global error states
# --------------------------------------------------------------------------- #


def test_dashboard_without_data_shows_coherent_empty_states() -> None:
    body = _page(service=_StubService(_empty_dashboard))
    assert "Sin ingresos en el período" in body
    assert "Sin leads con estos filtros" in body
    assert "Sin cartera activa" in body
    assert "Sin datos por categoría" in body
    assert "Sin asesores con cartera" in body


def test_partial_failure_reports_the_section_and_keeps_the_rest() -> None:
    service = _StubService(lambda: _full_dashboard(failed=("asesores",)))
    body = _page(service=service)
    assert "No fue posible calcular el resumen por asesor" in body
    assert "asesor-table" not in body
    # Unaffected sections still render with their real values.
    assert "1.842" in body
    assert "Casos por estado" in body


def test_failed_section_never_renders_as_zero() -> None:
    service = _StubService(lambda: _full_dashboard(failed=("casos_por_estado",)))
    body = _page(service=service)
    assert "No fue posible calcular la distribución por estado" in body
    assert "Sin leads con estos filtros" not in body


def test_global_error_returns_a_safe_page_without_internal_details() -> None:
    client = _client(_StubService(raise_global=True))
    _login(client, "ceo.local")
    response = client.get("/dashboard")
    assert response.status_code == 503
    assert "No fue posible cargar el Dashboard Ejecutivo" in response.text
    for leak in ("Traceback", "RuntimeError", "SELECT", "psycopg", "tpi.leads"):
        assert leak not in response.text


# --------------------------------------------------------------------------- #
# Filters
# --------------------------------------------------------------------------- #


def test_filters_are_a_get_form_with_labelled_controls() -> None:
    body = _page()
    assert 'method="get"' in body
    assert 'action="/dashboard"' in body
    for control in (
        "f-desde",
        "f-hasta",
        "f-granularidad",
        "f-asesor",
        "f-afp",
        "f-estado",
        "f-origen",
        "f-fuente",
    ):
        assert f'for="{control}"' in body
        assert f'id="{control}"' in body
    assert ">Aplicar<" in body
    assert ">Limpiar<" in body


def test_clear_button_points_to_the_unfiltered_url() -> None:
    body = _page(query="?estado=nuevo&fecha_desde=2026-09-01")
    assert '<a class="secondary" href="/dashboard">Limpiar</a>' in body


def test_selected_filters_are_preserved_in_the_form() -> None:
    body = _page(
        query="?fecha_desde=2026-08-19&fecha_hasta=2026-09-17&granularidad=mensual&estado=nuevo&asesor="
        + ADVISOR_ID
    )
    assert 'value="2026-08-19"' in body
    assert 'value="2026-09-17"' in body
    assert '<option value="mensual" selected>' in body
    assert '<option value="nuevo" selected>' in body
    assert f'<option value="{ADVISOR_ID}" selected>' in body


def test_invalid_range_returns_400_with_a_clear_message_and_no_query() -> None:
    service = _StubService()
    client = _client(service)
    _login(client, "ceo.local")
    response = client.get("/dashboard?fecha_desde=2026-09-20&fecha_hasta=2026-09-01")
    assert response.status_code == 400
    assert service.calls == 0
    assert "Revisa los filtros" in response.text
    assert "fecha_desde no puede ser mayor que fecha_hasta" in response.text
    assert 'value="2026-09-20"' in response.text


def test_quick_ranges_resolve_to_explicit_dates() -> None:
    body = _page()
    assert "Últimos 30 días" in body
    assert re.search(r"fecha_desde=\d{4}-\d{2}-\d{2}&amp;fecha_hasta=\d{4}-\d{2}-\d{2}", body)


def test_page_has_no_required_javascript_for_filtering() -> None:
    body = _page()
    assert "onclick" not in body
    assert "onsubmit" not in body
