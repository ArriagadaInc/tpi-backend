"""Presentacion de la agenda: resolucion del servicio y contexto de pantalla.

Mantiene fuera de las rutas la construccion del contexto de la tarjeta Reunion del
detalle del lead y la resolucion del servicio (que en produccion es una instancia real
y en las pruebas se inyecta con repositorios falsos). Todo fallo de base se degrada a un
aviso (``unavailable``) para que el resto del CRM siga funcionando (AC-5).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import Request

from app.auth.models import AuthenticatedUser
from app.database.errors import DatabaseAppError
from app.models.agenda import AGENDA_TZ
from app.services.agenda_service import AgendaService


def resolve_agenda_service(request: Request) -> AgendaService:
    service = getattr(request.app.state, "agenda_service", None)
    if isinstance(service, AgendaService):
        return service
    return AgendaService()


def _local(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(AGENDA_TZ)
    return value


def build_lead_agenda_context(
    agenda_service: AgendaService,
    lead_id: str,
    user: AuthenticatedUser,
) -> dict[str, Any]:
    """Contexto de la tarjeta Reunion (cita, responsables y permisos), fail-soft."""
    can_agendar = agenda_service.can_agendar(user)
    can_mark_attendance = agenda_service.can_mark_attendance(user)
    try:
        lead_uuid = UUID(str(lead_id))
    except (ValueError, TypeError, AttributeError):
        return {
            "cita": None,
            "responsables": [],
            "can_agendar": can_agendar,
            "can_mark_attendance": can_mark_attendance,
            "unavailable": True,
        }

    try:
        cita = agenda_service.get_cita_for_lead(lead_uuid)
        responsables = (
            agenda_service.get_responsables_para_agendar(lead_uuid, user) if can_agendar else []
        )
    except (DatabaseAppError, ValueError, TypeError):
        return {
            "cita": None,
            "responsables": [],
            "can_agendar": can_agendar,
            "can_mark_attendance": can_mark_attendance,
            "unavailable": True,
        }

    cita_view = None
    if cita is not None:
        cita_view = {
            "id_cita": str(cita["id_cita"]),
            "fecha_hora": _local(cita.get("fecha_hora")),
            "fecha_hora_fin": _local(cita.get("fecha_hora_fin")),
            "agendada_por_nombre": cita.get("agendada_por_nombre"),
            "canal": cita.get("canal"),
            "estado_cita": cita.get("estado_cita"),
            "link_reunion": cita.get("link_reunion"),
            "nota": cita.get("nota"),
            "motivo_cancelacion": cita.get("motivo_cancelacion"),
            "asesor_nombre": cita.get("asesor_nombre"),
        }

    responsables_view = [
        {"id_asesor": str(r["id_asesor"]), "nombre": r.get("nombre"), "rol": r.get("rol")}
        for r in responsables
    ]
    return {
        "cita": cita_view,
        "responsables": responsables_view,
        "can_agendar": can_agendar,
        "can_mark_attendance": can_mark_attendance,
        "unavailable": False,
    }
