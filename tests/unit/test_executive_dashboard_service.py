"""Unit tests for the executive dashboard service and its typed contract."""

from __future__ import annotations

from datetime import UTC, datetime

from app.auth.models import AuthenticatedUser
from app.models.executive_dashboard import DashboardFilters
from app.services.executive_dashboard_service import ExecutiveDashboardService


def _user(role: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        subject=f"{role}-subject",
        username=f"{role}.local",
        display_name=f"{role.title()} Demo",
        role=role,  # type: ignore[arg-type]
    )


class _FakeRepository:
    def get_kpi_snapshot(self, filters):
        return {"total_leads": 10, "cartera_activa": 7, "sin_asignar": 3}

    def get_estancados(self, filters, threshold_days=5):
        return 2

    def get_casos_por_estado(self, filters):
        return [
            {"estado": "nuevo", "n": 5},
            {"estado": "cerrado", "n": 3},
            {"estado": "estado_desconocido", "n": 2},
        ]

    def get_antiguedad(self, filters):
        return [{"bucket": "0-2", "n": 4}, {"bucket": "+30", "n": 3}]

    def get_estancados_por_antiguedad(self, filters, threshold_days=5):
        return [{"bucket": "+30", "n": 2}]

    def get_cartera_por_asesor(self, filters):
        return [
            {"id_asesor": None, "nombre": None, "cartera_total": 3, "cartera_activa": 3},
            {
                "id_asesor": "44444444-4444-4444-4444-444444444441",
                "nombre": "Asesor A",
                "cartera_total": 7,
                "cartera_activa": 4,
            },
        ]

    def get_metricas_operacionales_por_asesor(self, filters, threshold_days, cutover):
        return [
            {
                "id_asesor": None,
                "estancados": 1,
                "n_asignacion": 0,
                "tiempo_asignacion_dias": None,
                "n_primera_gestion": 0,
                "tiempo_primera_gestion_dias": None,
            },
            {
                "id_asesor": "44444444-4444-4444-4444-444444444441",
                "estancados": 1,
                "n_asignacion": 7,
                "tiempo_asignacion_dias": 0.1751,
                "n_primera_gestion": 3,
                "tiempo_primera_gestion_dias": 1.2,
            },
        ]

    def get_asesor_options(self):
        return [{"id_asesor": "44444444-4444-4444-4444-444444444441", "nombre": "Asesor A"}]

    def get_afp_options(self):
        return [{"id": "55555555-5555-5555-5555-555555555551", "nombre": "Habitat"}]

    def get_origen_options(self):
        return ["formulario_web"]

    def get_fuente_options(self):
        return ["backoffice"]

    def get_casos_por_estado_y_asesor(self, filters):
        return [
            {
                "id_asesor": "44444444-4444-4444-4444-444444444441",
                "nombre": "Asesor A",
                "estado": "nuevo",
                "n": 4,
            }
        ]

    def get_distribucion_afp(self, filters):
        return [{"categoria": "Habitat", "n": 6}, {"categoria": "Sin AFP", "n": 4}]

    def get_distribucion_origen(self, filters):
        return [{"categoria": "formulario_web", "n": 8}, {"categoria": "Sin origen", "n": 2}]

    def get_distribucion_fuente(self, filters):
        return [{"categoria": "backoffice", "n": 9}, {"categoria": "Sin fuente", "n": 1}]

    def get_leads_ingresados(self, filters):
        return 4

    def get_evolucion(self, filters):
        return [
            {"bucket": datetime(2026, 9, 1, tzinfo=UTC), "n": 2},
            {"bucket": datetime(2026, 9, 2, tzinfo=UTC), "n": 2},
        ]

    def get_funnel(self, filters, cutover=None):
        return {
            "cutover": "2026-09-01",
            "cobertura_completa": True,
            "excluidos_pre_cutover": 1,
            "denominador": 4,
            "steps": [{"origen": "nuevo", "destino": "contactado", "n": 2}],
            "bases": {"nuevo": 4},
        }

    def get_tiempo_asignacion(self, filters):
        return {"n": 5, "media_dias": 2.5}

    def get_tiempo_primera_gestion(self, filters, cutover=None):
        return {"n": 4, "media_dias": 1.25}


def _service() -> tuple[ExecutiveDashboardService, _FakeRepository]:
    repo = _FakeRepository()
    return ExecutiveDashboardService(repository=repo, settings=_settings()), repo


def _settings():
    from app.config import Settings

    return Settings(APP_ENV="testing", LEAD_STATE_HISTORY_CUTOVER="2026-09-01")


def test_can_access_only_ceo_and_cto() -> None:
    service, _ = _service()
    assert service.can_access(_user("ceo")) is True
    assert service.can_access(_user("cto")) is True
    for role in ("tester", "admin", "advisor", "executive", "operations", "readonly"):
        assert service.can_access(_user(role)) is False
    assert service.can_access(None) is False


def test_contract_exposes_both_scopes_explicitly() -> None:
    service, _ = _service()
    dashboard = service.build_executive_dashboard(DashboardFilters.from_raw())
    assert dashboard.current_snapshot.scope == "current_snapshot"
    assert dashboard.period_activity.scope == "period_activity"


def test_snapshot_kpis_are_mapped() -> None:
    service, _ = _service()
    dashboard = service.build_executive_dashboard(DashboardFilters.from_raw())
    snapshot = dashboard.current_snapshot
    assert snapshot.total_leads == 10
    assert snapshot.cartera_activa == 7
    assert snapshot.sin_asignar == 3
    assert snapshot.estancados == 2


def test_percentages_carry_numerator_and_denominator() -> None:
    service, _ = _service()
    dashboard = service.build_executive_dashboard(DashboardFilters.from_raw())
    bucket = dashboard.current_snapshot.casos_por_estado[0]
    assert bucket.n == 5
    assert bucket.denominador == 10
    assert bucket.percentage == 0.5


def test_unknown_states_are_preserved_with_safe_label() -> None:
    service, _ = _service()
    dashboard = service.build_executive_dashboard(DashboardFilters.from_raw())
    estados = {row.estado: row for row in dashboard.current_snapshot.casos_por_estado}
    assert "estado_desconocido" in estados
    assert estados["estado_desconocido"].label == "estado_desconocido"


def test_leads_without_asesor_have_own_bucket() -> None:
    service, _ = _service()
    dashboard = service.build_executive_dashboard(DashboardFilters.from_raw())
    by_id = {row.id_asesor: row for row in dashboard.current_snapshot.cartera_por_asesor}
    assert None in by_id
    assert by_id[None].nombre == "Sin asesor"


def test_funnel_rate_includes_base() -> None:
    service, _ = _service()
    dashboard = service.build_executive_dashboard(DashboardFilters.from_raw())
    step = dashboard.period_activity.funnel.steps[0]
    assert step.origen == "nuevo"
    assert step.destino == "contactado"
    assert step.n == 2
    assert step.base == 4
    assert step.rate == 0.5


def test_alerts_carry_filter_contract_for_linking() -> None:
    service, _ = _service()
    dashboard = service.build_executive_dashboard(DashboardFilters.from_raw())
    keys = {alert.key: alert for alert in dashboard.alerts}
    assert keys["sin_asignar"].count == 3
    assert keys["sin_asignar"].filters == {"sin_asignar": True}
    assert keys["estancados"].count == 2
    assert keys["estancados"].filters == {"estancado": True}


def test_contract_contains_no_lead_or_advisor_pii() -> None:
    service, _ = _service()
    dashboard = service.build_executive_dashboard(DashboardFilters.from_raw())
    payload = dashboard.to_dict()

    def _flatten(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield str(key).casefold()
                yield from _flatten(child)
        elif isinstance(value, list):
            for child in value:
                yield from _flatten(child)
        else:
            yield str(value).casefold()

    flattened = " ".join(_flatten(payload))
    for pii_token in ("rut", "email", "telefono", "nombre_completo", "password"):
        assert pii_token not in flattened


def test_contract_uses_only_mvp_categories() -> None:
    service, _ = _service()
    dashboard = service.build_executive_dashboard(DashboardFilters.from_raw())
    snapshot_keys = set(dashboard.current_snapshot.__dataclass_fields__)
    assert "genero" not in snapshot_keys
    assert "estado_civil" not in snapshot_keys
