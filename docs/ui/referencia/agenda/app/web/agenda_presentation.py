"""Presentacion de la agenda: resolucion del servicio y contexto de pantalla.

Mantiene fuera de las rutas la construccion del contexto de la tarjeta Reunion del
detalle del lead y la resolucion del servicio (que en produccion es una instancia real
y en las pruebas se inyecta con repositorios falsos). Todo fallo de base se degrada a un
aviso (``unavailable``) para que el resto del CRM siga funcionando (AC-5).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
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


# --------------------------------------------------------------------------------------
# Presentacion visual de la agenda (solo estetica: no cambia reglas ni permisos)
# --------------------------------------------------------------------------------------
HORA_INI = 9
HORA_FIN = 19
_MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
_DOW = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
PALETA = ("accent", "info", "violet", "warning")


def color_map(responsables: list[dict[str, Any]]) -> dict[str, str]:
    """Color estable por responsable (orden alfabetico), de los tonos del sistema visual."""
    nombres = sorted({str(r.get("nombre") or "") for r in responsables})
    return {n: PALETA[i % len(PALETA)] for i, n in enumerate(nombres)}


def rango_label(lunes: date) -> str:
    """'26 – 30 oct 2026' (viernes de la semana); con dos meses, '29 sep – 3 oct 2026'."""
    viernes = lunes + timedelta(days=4)
    if lunes.month == viernes.month:
        return f"{lunes.day} – {viernes.day} {_MESES[viernes.month - 1]} {viernes.year}"
    return f"{lunes.day} {_MESES[lunes.month - 1]} – {viernes.day} {_MESES[viernes.month - 1]} {viernes.year}"


def etiqueta_dia(dia: date, hoy: date) -> str:
    if dia == hoy:
        return "Hoy"
    if dia == hoy + timedelta(days=1):
        return "Mañana"
    return f"{_DOW[dia.weekday()].capitalize()} {dia.day} {_MESES[dia.month - 1]}"


def _asignar_carriles(eventos: list[dict[str, Any]]) -> None:
    """Reparte en carriles las reuniones que se superponen en el dia (varios responsables a la vez)."""
    eventos.sort(key=lambda e: (e["start"], e["dur"]))
    grupo: list[dict[str, Any]] = []
    fin_grupo = -1
    fines: list[int] = []

    def cerrar() -> None:
        for e in grupo:
            e["lanes"] = max(len(fines), 1)

    for e in eventos:
        if grupo and e["start"] >= fin_grupo:
            cerrar()
            grupo, fines, fin_grupo = [], [], -1
        carril = next((i for i, f in enumerate(fines) if f <= e["start"]), None)
        if carril is None:
            fines.append(e["start"] + e["dur"])
            carril = len(fines) - 1
        else:
            fines[carril] = e["start"] + e["dur"]
        e["lane"] = carril
        grupo.append(e)
        fin_grupo = max(fin_grupo, e["start"] + e["dur"])
    if grupo:
        cerrar()


def build_week_grid(
    citas: list[dict[str, Any]],
    lunes: date,
    hoy: date,
    ahora: datetime,
    colores: dict[str, str],
) -> list[dict[str, Any]]:
    """Dias habiles (lunes a viernes) con sus reuniones posicionadas por hora y carril."""
    dias: list[dict[str, Any]] = []
    for i in range(5):
        dia = lunes + timedelta(days=i)
        eventos: list[dict[str, Any]] = []
        for c in citas:
            ini, fin = c.get("fecha_hora"), c.get("fecha_hora_fin")
            if not isinstance(ini, datetime) or not isinstance(fin, datetime):
                continue
            if ini.astimezone(AGENDA_TZ).date() != dia:
                continue
            start = max(ini.hour * 60 + ini.minute - HORA_INI * 60, 0)
            dur = max(int((fin - ini).total_seconds() // 60), 15)
            eventos.append(
                {"cita": c, "start": start, "dur": dur, "color": colores.get(str(c.get("asesor_nombre")), "slate")}
            )
        _asignar_carriles(eventos)
        ahora_min = ahora.hour * 60 + ahora.minute - HORA_INI * 60
        dias.append(
            {
                "dow": _DOW[dia.weekday()],
                "dia": dia.day,
                "mes": _MESES[dia.month - 1],
                "fecha": dia,
                "es_hoy": dia == hoy,
                "ahora": ahora_min if dia == hoy and 0 <= ahora_min <= (HORA_FIN - HORA_INI) * 60 else None,
                "eventos": eventos,
            }
        )
    return dias


def resumen_semana(citas: list[dict[str, Any]]) -> dict[str, int]:
    conteo = {"agendada": 0, "realizada": 0, "no_asistio": 0, "cancelada": 0}
    for c in citas:
        estado = str(c.get("estado_cita"))
        if estado in conteo:
            conteo[estado] += 1
    return conteo


def agrupar_por_dia(citas: list[dict[str, Any]], hoy: date, colores: dict[str, str]) -> list[dict[str, Any]]:
    grupos: dict[date, list[dict[str, Any]]] = {}
    for c in citas:
        ini = c.get("fecha_hora")
        if isinstance(ini, datetime):
            dur = int((c["fecha_hora_fin"] - ini).total_seconds() // 60) if isinstance(c.get("fecha_hora_fin"), datetime) else 30
            grupos.setdefault(ini.astimezone(AGENDA_TZ).date(), []).append(
                {"cita": c, "dur": dur, "color": colores.get(str(c.get("asesor_nombre")), "slate")}
            )
    return [
        {"label": etiqueta_dia(d, hoy), "fecha": d, "es_hoy": d == hoy, "reuniones": sorted(v, key=lambda x: x["cita"]["fecha_hora"])}
        for d, v in sorted(grupos.items())
    ]


def meeting_tile(cita_dt: datetime, hoy: date) -> dict[str, Any]:
    """Datos de la 'ficha de fecha' y del texto relativo de la tarjeta Reunion."""
    local = cita_dt.astimezone(AGENDA_TZ)
    dias = (local.date() - hoy).days
    relativo = "Hoy" if dias == 0 else "Mañana" if dias == 1 else f"En {dias} días" if dias > 1 else "Ya pasó"
    return {"mes": _MESES[local.month - 1].upper(), "dia": local.day, "dow": _DOW[local.weekday()].upper(), "relativo": relativo}


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
    try:
        colores = color_map(agenda_service.list_responsables())
    except (DatabaseAppError, ValueError, TypeError):
        colores = {}
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
            "color": colores.get(str(cita.get("asesor_nombre")), "slate"),
        }
        if isinstance(cita_view["fecha_hora"], datetime):
            cita_view["tile"] = meeting_tile(cita_view["fecha_hora"], datetime.now(AGENDA_TZ).date())

    responsables_view = [
        {
            "id_asesor": str(r["id_asesor"]),
            "nombre": r.get("nombre"),
            "rol": r.get("rol"),
            "color": colores.get(str(r.get("nombre")), "slate"),
        }
        for r in responsables
    ]
    return {
        "cita": cita_view,
        "responsables": responsables_view,
        "can_agendar": can_agendar,
        "can_mark_attendance": can_mark_attendance,
        "unavailable": False,
    }
