"""Agenda de reuniones del CRM: contratos de dominio.

Contiene las constantes canónicas de la agenda (estados, modalidades, duraciones y
ventana de horario laboral), las excepciones de dominio que la capa web traduce a
códigos HTTP y las validaciones puras de horario que el servicio aplica siempre en el
servidor (la interfaz solo guía).

Fuente de verdad: ``docs/AGENDA_REUNIONES_DISENO.md`` (secciones 2, 3 y 4) y la
migración 010 (``scripts/sql/010_extend_citas_agenda.sql``), que fija el CHECK de
``tpi.citas.estado_cita``.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

AGENDA_TZ = ZoneInfo("America/Santiago")

# Estados de una reunion (CHECK de tpi.citas.estado_cita, migracion 010).
CITA_ESTADO_AGENDADA = "agendada"
CITA_ESTADO_REALIZADA = "realizada"
CITA_ESTADO_NO_ASISTIO = "no_asistio"
CITA_ESTADO_CANCELADA = "cancelada"
CITA_ESTADOS = (
    CITA_ESTADO_AGENDADA,
    CITA_ESTADO_REALIZADA,
    CITA_ESTADO_NO_ASISTIO,
    CITA_ESTADO_CANCELADA,
)

CITA_ESTADO_LABELS: dict[str, str] = {
    CITA_ESTADO_AGENDADA: "Agendada",
    CITA_ESTADO_REALIZADA: "Realizada",
    CITA_ESTADO_NO_ASISTIO: "No asistió",
    CITA_ESTADO_CANCELADA: "Cancelada",
}

# Modalidad de la reunion (columna tpi.citas.canal, decision 8 supuesto I).
CITA_MODALIDAD_MEET = "Google Meet"
CITA_MODALIDAD_LLAMADA = "Llamada"
CITA_MODALIDAD_PRESENCIAL = "Presencial"
CITA_MODALIDADES = (CITA_MODALIDAD_MEET, CITA_MODALIDAD_LLAMADA, CITA_MODALIDAD_PRESENCIAL)

# Duraciones permitidas en minutos (30 por defecto; supuesto C).
CITA_DURACIONES = (30, 45, 60)
CITA_DURACION_DEFAULT = 30

# Ventana de horario laboral (America/Santiago; supuesto B).
HORARIO_INICIO = time(9, 0)
HORARIO_FIN = time(19, 0)
INCREMENTO_MINUTOS = 15

MAX_NOTA_LEN = 500

# Estados de lead que no admiten agendar (seccion 4 del diseño).
LEAD_INACTIVO_PARA_AGENDA = frozenset(
    {"cerrado", "perdido", "no_interesado", "datos_erroneos", "no_contactado"}
)


def cita_estado_label(value: str | None) -> str:
    if value is None:
        return ""
    return CITA_ESTADO_LABELS.get(value, str(value))


class AgendaError(Exception):
    """Base de los errores de dominio de la agenda; lleva el codigo HTTP asociado."""

    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AgendaValidationError(AgendaError):
    """Violacion de una regla de negocio de la agenda (400)."""


class AgendaConflictError(AgendaError):
    """Superposicion de horario o reunion duplicada (409)."""

    status_code = 409


class AgendaPermissionError(AgendaError):
    """El actor no tiene permiso para la accion (403)."""

    status_code = 403


class AgendaNotFoundError(AgendaError):
    """El lead o la reunion no existe o esta fuera del alcance del actor (404)."""

    status_code = 404


def validate_duracion(duracion: int) -> int:
    if duracion not in CITA_DURACIONES:
        raise AgendaValidationError("La duración debe ser 30, 45 o 60 minutos")
    return duracion


def validate_modalidad(modalidad: str) -> str:
    normalized = " ".join(str(modalidad).strip().split())
    if normalized not in CITA_MODALIDADES:
        raise AgendaValidationError("La modalidad no es válida")
    return normalized


def validate_nota(nota: str | None) -> str | None:
    if nota is None:
        return None
    normalized = " ".join(str(nota).strip().split())
    if not normalized:
        return None
    if len(normalized) > MAX_NOTA_LEN:
        raise AgendaValidationError(f"La nota no puede superar {MAX_NOTA_LEN} caracteres")
    return normalized


def validate_inicio(inicio: datetime) -> datetime:
    """Valida el inicio: con zona horaria, lunes a viernes, cada 15 minutos, desde 09:00."""
    if inicio.tzinfo is None:
        raise AgendaValidationError("La fecha y hora deben llevar zona horaria")
    local = inicio.astimezone(AGENDA_TZ)
    if local.weekday() >= 5:
        raise AgendaValidationError("Las reuniones solo se agendan de lunes a viernes")
    if local.time() < HORARIO_INICIO:
        raise AgendaValidationError("Las reuniones comienzan a las 09:00")
    if local.second != 0 or local.microsecond != 0:
        raise AgendaValidationError("El inicio debe caer cada 15 minutos")
    if local.minute % INCREMENTO_MINUTOS != 0:
        raise AgendaValidationError("El inicio debe caer cada 15 minutos")
    return inicio


def validate_fin_dentro_de_horario(inicio: datetime, duracion: int) -> datetime:
    fin = inicio + timedelta(minutes=duracion)
    if fin.astimezone(AGENDA_TZ).time() > HORARIO_FIN:
        raise AgendaValidationError("Las reuniones deben terminar a más tardar a las 19:00")
    return fin


def validate_no_en_pasado(inicio: datetime, ahora: datetime | None = None) -> datetime:
    referencia = ahora if ahora is not None else datetime.now(AGENDA_TZ)
    if inicio <= referencia:
        raise AgendaValidationError("No se puede agendar en el pasado")
    return inicio


def build_agenda_datetime(fecha: str, hora: str) -> datetime:
    """Construye un datetime aware en America/Santiago desde fecha (YYYY-MM-DD) y hora (HH:MM)."""
    try:
        dia = date.fromisoformat(fecha)
    except (ValueError, TypeError) as exc:
        raise AgendaValidationError("La fecha no es válida") from exc

    try:
        partes = str(hora).strip().split(":")
        if len(partes) not in (2, 3):
            raise ValueError
        hh = int(partes[0])
        mm = int(partes[1])
        horario = time(hh, mm)
    except (ValueError, TypeError, AttributeError) as exc:
        raise AgendaValidationError("La hora no es válida") from exc

    return datetime.combine(dia, horario, tzinfo=AGENDA_TZ)
