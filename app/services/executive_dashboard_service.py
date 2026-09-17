"""Application service for the Executive CRM Dashboard (H3.3.4, Parte B).

Coordinates the aggregate repository queries and assembles the typed response
contract with the two explicit scopes (``current_snapshot`` vs
``period_activity``). Access is server-side only: ``ceo``/``cto`` (superusers);
the caller must reject any other role before invoking this service so that no
dashboard query runs for unauthorized access.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.auth.models import AuthenticatedUser, is_superuser
from app.config import Settings, get_settings
from app.models.crm_states import crm_state_label
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
    estancamiento_dias_default,
    percentage,
)
from app.repositories.executive_dashboard_repository import ExecutiveDashboardRepository

_SIN_ASESOR_LABEL = "Sin asesor"


class ExecutiveDashboardService:
    """Builds the executive dashboard contract from aggregate repository data."""

    def __init__(
        self,
        repository: ExecutiveDashboardRepository | None = None,
        settings: Settings | None = None,
        *,
        estancamiento_dias: int = estancamiento_dias_default(),
    ) -> None:
        self.repository = repository or ExecutiveDashboardRepository()
        self.settings = settings or get_settings()
        self.estancamiento_dias = estancamiento_dias

    def can_access(self, user: AuthenticatedUser | None) -> bool:
        """Return True only for superuser roles (ceo, cto)."""
        return user is not None and is_superuser(user.role)

    @property
    def cutover(self) -> date | None:
        return self.settings.lead_state_history_cutover

    def build_executive_dashboard(self, filters: DashboardFilters) -> ExecutiveDashboard:
        """Assemble both scopes from bounded aggregate queries (no per-lead fan-out)."""
        snapshot = self._build_snapshot(filters)
        period = self._build_period(filters)
        alerts = [
            AlertTarget(
                key="sin_asignar", count=snapshot.sin_asignar, filters={"sin_asignar": True}
            ),
            AlertTarget(key="estancados", count=snapshot.estancados, filters={"estancado": True}),
        ]
        return ExecutiveDashboard(
            filters=filters,
            current_snapshot=snapshot,
            period_activity=period,
            alerts=alerts,
        )

    def _build_snapshot(self, filters: DashboardFilters) -> CurrentSnapshot:
        kpis = self.repository.get_kpi_snapshot(filters)
        total = kpis["total_leads"]
        cartera_activa = kpis["cartera_activa"]
        estancados = self.repository.get_estancados(filters, self.estancamiento_dias)

        casos = self.repository.get_casos_por_estado(filters)
        casos_por_estado = [
            EstadoBucket(
                estado=str(row["estado"]),
                label=crm_state_label(row["estado"]),
                n=int(row["n"]),
                denominador=total,
                percentage=percentage(int(row["n"]), total),
            )
            for row in casos
        ]

        antiguedad = [
            AntiguedadBucket(
                bucket=str(row["bucket"]),
                n=int(row["n"]),
                denominador=cartera_activa,
                percentage=percentage(int(row["n"]), cartera_activa),
            )
            for row in self.repository.get_antiguedad(filters)
        ]

        estancados_por_antiguedad = [
            AntiguedadBucket(
                bucket=str(row["bucket"]),
                n=int(row["n"]),
                denominador=estancados,
                percentage=percentage(int(row["n"]), estancados),
            )
            for row in self.repository.get_estancados_por_antiguedad(
                filters, self.estancamiento_dias
            )
        ]

        cartera_por_asesor = [
            AsesorRow(
                id_asesor=str(row["id_asesor"]) if row.get("id_asesor") is not None else None,
                nombre=self._asesor_nombre(row.get("nombre")),
                cartera_total=int(row["cartera_total"]),
                cartera_activa=int(row["cartera_activa"]),
            )
            for row in self.repository.get_cartera_por_asesor(filters)
        ]

        casos_por_estado_y_asesor = [
            EstadoAsesorCell(
                id_asesor=str(row["id_asesor"]) if row.get("id_asesor") is not None else None,
                nombre=self._asesor_nombre(row.get("nombre")),
                estado=str(row["estado"]),
                estado_label=crm_state_label(row["estado"]),
                n=int(row["n"]),
            )
            for row in self.repository.get_casos_por_estado_y_asesor(filters)
        ]

        return CurrentSnapshot(
            total_leads=total,
            cartera_activa=cartera_activa,
            sin_asignar=kpis["sin_asignar"],
            estancados=estancados,
            casos_por_estado=casos_por_estado,
            antiguedad=antiguedad,
            estancados_por_antiguedad=estancados_por_antiguedad,
            cartera_por_asesor=cartera_por_asesor,
            casos_por_estado_y_asesor=casos_por_estado_y_asesor,
            distribucion_afp=self._distribucion(
                self.repository.get_distribucion_afp(filters), total
            ),
            distribucion_origen=self._distribucion(
                self.repository.get_distribucion_origen(filters), total
            ),
            distribucion_fuente=self._distribucion(
                self.repository.get_distribucion_fuente(filters), total
            ),
        )

    def _build_period(self, filters: DashboardFilters) -> PeriodActivity:
        leads_ingresados = self.repository.get_leads_ingresados(filters)
        evolucion = [
            EvolucionPoint(bucket=self._bucket_label(row["bucket"]), n=int(row["n"]))
            for row in self.repository.get_evolucion(filters)
        ]
        funnel = self._build_funnel(filters)
        tiempo_asignacion = self.repository.get_tiempo_asignacion(filters)
        tiempo_gestion = self.repository.get_tiempo_primera_gestion(filters, self.cutover)
        return PeriodActivity(
            leads_ingresados=leads_ingresados,
            evolucion=evolucion,
            funnel=funnel,
            tiempo_asignacion=self._tiempo(tiempo_asignacion),
            tiempo_primera_gestion=self._tiempo(tiempo_gestion),
        )

    def _build_funnel(self, filters: DashboardFilters) -> Funnel:
        raw = self.repository.get_funnel(filters, self.cutover)
        bases: dict[str, int] = raw.get("bases") or {}
        steps = [
            FunnelStep(
                origen=str(step["origen"]),
                destino=str(step["destino"]),
                origen_label=crm_state_label(step["origen"]),
                destino_label=crm_state_label(step["destino"]),
                n=int(step["n"]),
                base=int(bases.get(step["origen"], 0)),
                rate=percentage(int(step["n"]), int(bases.get(step["origen"], 0))),
            )
            for step in raw.get("steps") or []
        ]
        return Funnel(
            scope="period_activity",
            cutover=raw.get("cutover"),
            cobertura_completa=bool(raw.get("cobertura_completa")),
            excluidos_pre_cutover=int(raw.get("excluidos_pre_cutover") or 0),
            denominador=int(raw.get("denominador") or 0),
            steps=steps,
        )

    @staticmethod
    def _distribucion(rows: list[dict[str, Any]], denominador: int) -> list[DistribucionBucket]:
        return [
            DistribucionBucket(
                categoria=str(row["categoria"]),
                n=int(row["n"]),
                denominador=denominador,
                percentage=percentage(int(row["n"]), denominador),
            )
            for row in rows
        ]

    @staticmethod
    def _tiempo(raw: dict[str, Any]) -> TiempoMetric:
        media = raw.get("media_dias")
        return TiempoMetric(
            n=int(raw.get("n") or 0),
            media_dias=round(float(media), 2) if media is not None else None,
        )

    @staticmethod
    def _bucket_label(value: Any) -> str:
        if value is None:
            return ""
        if hasattr(value, "date"):
            return str(value.date().isoformat())
        return str(value)

    @staticmethod
    def _asesor_nombre(nombre: Any) -> str | None:
        if nombre is None:
            return _SIN_ASESOR_LABEL
        return str(nombre)
