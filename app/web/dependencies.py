"""Web-layer dependencies and local fallback data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from app.components.ui import get_public_simulator_url
from app.config import get_settings
from app.models.crm_states import CRM_STATE_CONTRACT
from app.services import SolicitudService


class LeadBoardService(Protocol):
    """Subset of service methods the web UX needs."""

    def get_crm_bandeja(self, *args: Any, **kwargs: Any) -> dict[str, Any]: ...

    def get_crm_estado_lead_options(self) -> list[str]: ...

    def get_catalogo_afp(self) -> list[dict[str, Any]]: ...

    def get_solicitud_detalle(self, id_lead: Any) -> dict[str, Any] | None: ...

    def get_solicitud_detalle_masked(self, id_lead: Any) -> dict[str, Any] | None: ...

    def delete_test_lead(self, id_lead: Any) -> Any: ...

    def is_test_lead_cleanup_enabled(self) -> bool: ...

    def get_solicitudes_por_rut(self, rut: str, masked: bool = True) -> list[dict[str, Any]]: ...

    def update_lead_status(self, id_lead: Any, estado_lead: str) -> bool: ...

    def append_lead_comment(self, id_lead: Any, comment_text: str, author: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class WebLeadOption:
    value: str
    label: str


MOCK_BOARD_ROWS: list[dict[str, Any]] = [
    {
        "id_lead": "11111111-1111-1111-1111-111111111111",
        "nombre_completo": "Juan Perez",
        "rut": "12.345.678-5",
        "telefono": "+56 9 1234 5678",
        "afp": "Habitat",
        "saldo_afp": 5120000,
        "estado_lead": "nuevo",
        "comentarios": "Lead de ejemplo para la interfaz web.",
        "created_at": datetime(2026, 8, 21, 9, 45),
    },
    {
        "id_lead": "22222222-2222-2222-2222-222222222222",
        "nombre_completo": "Maria Soto",
        "rut": "15.234.567-8",
        "telefono": "+56 9 8765 4321",
        "afp": "Cuprum",
        "saldo_afp": 2243000,
        "estado_lead": "contactado",
        "comentarios": "Seguimiento comercial en curso.",
        "created_at": datetime(2026, 8, 21, 11, 20),
    },
    {
        "id_lead": "33333333-3333-3333-3333-333333333333",
        "nombre_completo": "Carla Rojas",
        "rut": "18.765.432-1",
        "telefono": "+56 9 5555 1212",
        "afp": "Provida",
        "saldo_afp": 6789000,
        "estado_lead": "cerrado",
        "comentarios": "Esperando validacion de antecedentes.",
        "created_at": datetime(2026, 8, 20, 16, 5),
    },
]

MOCK_AFP_OPTIONS: list[dict[str, Any]] = [
    {"id": "00000000-0000-0000-0000-000000000001", "nombre": "Habitat"},
    {"id": "00000000-0000-0000-0000-000000000002", "nombre": "Cuprum"},
    {"id": "00000000-0000-0000-0000-000000000003", "nombre": "Provida"},
]

MOCK_ESTADOS: list[str] = list(CRM_STATE_CONTRACT)


def get_web_service(factory: type[SolicitudService] | None = None) -> LeadBoardService:
    """Return the application service instance used by the web UI."""
    resolved_factory = factory or SolicitudService
    return resolved_factory()


def has_real_data_source(service: LeadBoardService) -> bool:
    """Detect whether the web can talk to the real CRM service."""
    return not isinstance(service, _MockLeadBoardService)


class _MockLeadBoardService:
    """Tiny local-only fallback for the first UX iteration."""

    def get_crm_bandeja(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        page = int(kwargs.get("page", 1))
        page_size = int(kwargs.get("page_size", 20))
        search = str(kwargs.get("search") or "").strip().casefold()
        estado = str(kwargs.get("estado_lead") or "").strip().casefold()
        afp_id = kwargs.get("afp_id")
        date_from = kwargs.get("date_from")
        date_to = kwargs.get("date_to")
        sort_by = str(kwargs.get("sort_by") or "created_at").strip()
        sort_direction = str(kwargs.get("sort_direction") or "desc").strip().lower()

        rows = list(MOCK_BOARD_ROWS)
        if search:
            rows = [
                row
                for row in rows
                if search in str(row["nombre_completo"]).casefold()
                or search in str(row["rut"]).casefold()
            ]
        if estado:
            rows = [row for row in rows if str(row["estado_lead"]).casefold() == estado]
        if afp_id:
            afp_name = next(
                (option["nombre"] for option in MOCK_AFP_OPTIONS if option["id"] == str(afp_id)),
                None,
            )
            if afp_name:
                rows = [row for row in rows if str(row["afp"]).casefold() == afp_name.casefold()]
        if date_from:
            rows = [row for row in rows if _row_date(row) >= _as_date(date_from)]
        if date_to:
            rows = [row for row in rows if _row_date(row) <= _as_date(date_to)]

        reverse = sort_direction != "asc"
        if sort_by == "nombre_completo":
            rows.sort(key=lambda row: str(row["nombre_completo"]).casefold(), reverse=reverse)
        elif sort_by == "rut":
            rows.sort(key=lambda row: str(row["rut"]), reverse=reverse)
        elif sort_by == "afp":
            rows.sort(key=lambda row: str(row["afp"]).casefold(), reverse=reverse)
        else:
            rows.sort(key=lambda row: row["created_at"], reverse=reverse)

        total = len(rows)
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "solicitudes": rows[start:end],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }

    def get_crm_estado_lead_options(self) -> list[str]:
        return list(MOCK_ESTADOS)

    def get_catalogo_afp(self) -> list[dict[str, Any]]:
        return list(MOCK_AFP_OPTIONS)

    def get_solicitud_detalle(self, id_lead: Any) -> dict[str, Any] | None:
        for row in MOCK_BOARD_ROWS:
            if str(row["id_lead"]) == str(id_lead):
                return dict(row)
        return None

    def get_solicitud_detalle_masked(self, id_lead: Any) -> dict[str, Any] | None:
        for row in MOCK_BOARD_ROWS:
            if str(row["id_lead"]) == str(id_lead):
                return dict(row)
        return None

    def delete_test_lead(self, id_lead: Any) -> Any:
        return None

    def is_test_lead_cleanup_enabled(self) -> bool:
        return True

    def get_solicitudes_por_rut(self, rut: str, masked: bool = True) -> list[dict[str, Any]]:
        return [row for row in MOCK_BOARD_ROWS if row["rut"] == rut]

    def update_lead_status(self, id_lead: Any, estado_lead: str) -> bool:
        for row in MOCK_BOARD_ROWS:
            if str(row["id_lead"]) == str(id_lead):
                if estado_lead not in CRM_STATE_CONTRACT:
                    raise ValueError("Estado de lead invalido")
                row["estado_lead"] = estado_lead
                return True
        return False

    def append_lead_comment(self, id_lead: Any, comment_text: str, author: str) -> bool:
        for row in MOCK_BOARD_ROWS:
            if str(row["id_lead"]) == str(id_lead):
                existing = str(row.get("comentarios") or "")
                fragment = f"[demo] {author}\n{comment_text}"
                row["comentarios"] = f"{existing}\n\n{fragment}".strip() if existing else fragment
                return True
        return False


def build_service_for_web(real_service: LeadBoardService | None = None) -> LeadBoardService:
    return real_service or SolicitudService()


def resolve_web_simulator_url() -> str | None:
    """Return the approved simulator URL from centralized configuration."""
    settings = get_settings()
    return get_public_simulator_url(settings)


def _row_date(row: dict[str, Any]) -> date:
    created_at = row["created_at"]
    if isinstance(created_at, datetime):
        return created_at.date()
    if isinstance(created_at, date):
        return created_at
    return date.today()


def _as_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.fromisoformat(str(value)).date()
