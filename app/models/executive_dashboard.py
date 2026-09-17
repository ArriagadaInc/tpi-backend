"""Typed data contracts for the Executive CRM Dashboard (H3.3.4, Parte B).

The dashboard exposes two explicitly separated scopes so that the temporal
range never silently turns a current snapshot into an ingestion cohort:

- ``current_snapshot``: the state as of the moment of the query (total leads,
  active portfolio, unassigned, stuck, cases by state, age, per-advisor
  portfolio, current AFP/origin/source distribution). Dimension filters
  (estado, asesor, AFP, origen, fuente) apply; the date range does NOT restrict
  these metrics.
- ``period_activity``: metrics computed over ``fecha_ingreso`` inside the
  selected range (leads ingested, daily/weekly/monthly evolution, observable
  funnel and temporal metrics).

Every count uses ``COUNT(DISTINCT id_lead)`` when a join could fan out, and
every percentage carries its numerator and denominator. No lead PII is present
in any contract; advisors are exposed only as technical id + visible name plus
aggregate metrics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal
from uuid import UUID

from app.models.crm_states import crm_state_label

DashboardGranularity = Literal["diaria", "semanal", "mensual"]

GRANULARITY_VALUES: tuple[str, ...] = ("diaria", "semanal", "mensual")

# Safe, explicit PostgreSQL truncation targets; values are constrained by the
# GRANULARITY_VALUES whitelist and never interpolated from raw user input.
_GRANULARITY_SQL_FIELD: dict[str, str] = {
    "diaria": "day",
    "semanal": "week",
    "mensual": "month",
}

# Buckets de antigüedad en días corridos (calendario), no hábiles.
ANTIGUEDAD_BUCKETS: tuple[str, ...] = ("0-2", "3-7", "8-15", "16-30", "+30")

# Estados excluidos de la cartera activa (definición humana literal).
CARTERA_INACTIVA_ESTADOS: tuple[str, ...] = ("cerrado", "perdido", "no_califica", "duplicado")

SNAPSHOT_SCOPE = "current_snapshot"
PERIOD_SCOPE = "period_activity"

_DEFAULT_GRANULARIDAD: DashboardGranularity = "diaria"
_DEFAULT_ESTANCAMIENTO_DIAS = 5


def granularity_sql_field(granularidad: str) -> str:
    """Return the whitelisted SQL date_trunc field for a granularity value."""
    return _GRANULARITY_SQL_FIELD[granularidad]


def estancamiento_dias_default() -> int:
    """Operational rule threshold (configurable; default 5 calendar days)."""
    return _DEFAULT_ESTANCAMIENTO_DIAS


def percentage(n: int, denominador: int) -> float | None:
    """Return n/denominador as a fraction, or None when the denominator is zero."""
    if denominador <= 0:
        return None
    return round(n / denominador, 4)


@dataclass(frozen=True, slots=True)
class DashboardFilters:
    """Validated, parameterized filter object for the executive dashboard."""

    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    granularidad: DashboardGranularity = _DEFAULT_GRANULARIDAD
    estado: str | None = None
    asesor: UUID | None = None
    afp: UUID | None = None
    origen: str | None = None
    fuente: str | None = None

    @property
    def period_active(self) -> bool:
        return self.fecha_desde is not None or self.fecha_hasta is not None

    @classmethod
    def from_raw(
        cls,
        *,
        fecha_desde: str | date | None = None,
        fecha_hasta: str | date | None = None,
        granularidad: str | None = None,
        estado: str | None = None,
        asesor: str | UUID | None = None,
        afp: str | UUID | None = None,
        origen: str | None = None,
        fuente: str | None = None,
    ) -> DashboardFilters:
        """Parse and validate raw filter inputs, failing closed on invalid ranges."""
        desde = cls._parse_date(fecha_desde, "fecha_desde")
        hasta = cls._parse_date(fecha_hasta, "fecha_hasta")
        if desde is not None and hasta is not None and desde > hasta:
            raise ValueError("fecha_desde no puede ser mayor que fecha_hasta")

        return cls(
            fecha_desde=desde,
            fecha_hasta=hasta,
            granularidad=cls._normalize_granularidad(granularidad),
            estado=cls._normalize_estado(estado),
            asesor=cls._parse_uuid(asesor, "asesor"),
            afp=cls._parse_uuid(afp, "afp"),
            origen=cls._normalize_text(origen),
            fuente=cls._normalize_text(fuente),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["fecha_desde"] = (
            self.fecha_desde.isoformat() if self.fecha_desde is not None else None
        )
        payload["fecha_hasta"] = (
            self.fecha_hasta.isoformat() if self.fecha_hasta is not None else None
        )
        payload["asesor"] = str(self.asesor) if self.asesor is not None else None
        payload["afp"] = str(self.afp) if self.afp is not None else None
        return payload

    @staticmethod
    def _parse_date(value: str | date | None, label: str) -> date | None:
        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value).strip())
        except ValueError as exc:
            raise ValueError(f"{label} debe ser una fecha ISO valida") from exc

    @staticmethod
    def _normalize_granularidad(value: str | None) -> DashboardGranularity:
        if value is None or value == "":
            return _DEFAULT_GRANULARIDAD
        normalized = str(value).strip().casefold()
        if normalized not in GRANULARITY_VALUES:
            raise ValueError(f"granularidad debe ser una de: {', '.join(GRANULARITY_VALUES)}")
        return normalized  # type: ignore[return-value]

    @staticmethod
    def _normalize_estado(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).strip().split())
        if not normalized:
            return None
        # Preserve the canonical value when known; otherwise keep the raw
        # casefolded value so unknown states still filter safely (no crash).
        return normalized.casefold()

    @staticmethod
    def _parse_uuid(value: str | UUID | None, label: str) -> UUID | None:
        if value is None or value == "":
            return None
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value).strip())
        except (ValueError, AttributeError) as exc:
            raise ValueError(f"{label} debe ser un identificador valido") from exc

    @staticmethod
    def _normalize_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).strip().split())
        return normalized or None


@dataclass(frozen=True, slots=True)
class EstadoBucket:
    estado: str
    label: str
    n: int
    denominador: int
    percentage: float | None


@dataclass(frozen=True, slots=True)
class AntiguedadBucket:
    bucket: str
    n: int
    denominador: int
    percentage: float | None


@dataclass(frozen=True, slots=True)
class DistribucionBucket:
    categoria: str
    n: int
    denominador: int
    percentage: float | None


@dataclass(frozen=True, slots=True)
class AsesorRow:
    id_asesor: str | None
    nombre: str | None
    cartera_total: int
    cartera_activa: int


@dataclass(frozen=True, slots=True)
class EstadoAsesorCell:
    id_asesor: str | None
    nombre: str | None
    estado: str
    estado_label: str
    n: int


@dataclass(frozen=True, slots=True)
class EvolucionPoint:
    bucket: str
    n: int


@dataclass(frozen=True, slots=True)
class FunnelStep:
    origen: str
    destino: str
    origen_label: str
    destino_label: str
    n: int
    base: int
    rate: float | None


@dataclass(frozen=True, slots=True)
class TiempoMetric:
    n: int
    media_dias: float | None


@dataclass(frozen=True, slots=True)
class Funnel:
    scope: str
    cutover: str | None
    cobertura_completa: bool
    excluidos_pre_cutover: int
    denominador: int
    steps: list[FunnelStep]


@dataclass(frozen=True, slots=True)
class CurrentSnapshot:
    scope: str = SNAPSHOT_SCOPE
    total_leads: int = 0
    cartera_activa: int = 0
    sin_asignar: int = 0
    estancados: int = 0
    casos_por_estado: list[EstadoBucket] = field(default_factory=list)
    antiguedad: list[AntiguedadBucket] = field(default_factory=list)
    estancados_por_antiguedad: list[AntiguedadBucket] = field(default_factory=list)
    cartera_por_asesor: list[AsesorRow] = field(default_factory=list)
    casos_por_estado_y_asesor: list[EstadoAsesorCell] = field(default_factory=list)
    distribucion_afp: list[DistribucionBucket] = field(default_factory=list)
    distribucion_origen: list[DistribucionBucket] = field(default_factory=list)
    distribucion_fuente: list[DistribucionBucket] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PeriodActivity:
    scope: str = PERIOD_SCOPE
    leads_ingresados: int = 0
    evolucion: list[EvolucionPoint] = field(default_factory=list)
    funnel: Funnel = field(
        default_factory=lambda: Funnel(
            scope=PERIOD_SCOPE,
            cutover=None,
            cobertura_completa=False,
            excluidos_pre_cutover=0,
            denominador=0,
            steps=[],
        )
    )
    tiempo_asignacion: TiempoMetric = field(
        default_factory=lambda: TiempoMetric(n=0, media_dias=None)
    )
    tiempo_primera_gestion: TiempoMetric = field(
        default_factory=lambda: TiempoMetric(n=0, media_dias=None)
    )


@dataclass(frozen=True, slots=True)
class AlertTarget:
    """Contract for linking alerts to the existing lead listing later on.

    ``filters`` describes the real filter params the listing must accept; it is
    not a decorative or nonexistent URL. The current ``/leads`` listing does not
    yet support ``sin_asignar``/``estancado`` (documented in the requirements
    matrix); this contract pins the extension needed for the visual session.
    """

    key: str
    count: int
    filters: dict[str, bool]


@dataclass(frozen=True, slots=True)
class ExecutiveDashboard:
    filters: DashboardFilters
    current_snapshot: CurrentSnapshot
    period_activity: PeriodActivity
    alerts: list[AlertTarget]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def estado_label(value: str | None) -> str:
    """Return the safe display label for a raw state, preserving unknowns."""
    return crm_state_label(value)
