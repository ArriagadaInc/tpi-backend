"""Servicio de negocio de la agenda de reuniones del CRM.

El servidor es la fuente de verdad: valida horario, responsable y permisos contra la
base, resuelve el alcance de cartera con la cadena existente (``has_portfolio_scope`` y
``resolve_advisor_identity``) y delega la escritura transaccional en el repositorio, que
reutiliza ``update_lead_status`` para el cambio de estado del lead. Ningun permiso se
amplia: toda accion se deniega si el actor no cumple la regla (fail-closed).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from app.auth.models import AuthenticatedUser, has_portfolio_scope, is_superuser
from app.models.agenda import (
    AGENDA_TZ,
    AgendaNotFoundError,
    AgendaPermissionError,
    AgendaValidationError,
    build_agenda_datetime,
    validate_duracion,
    validate_fin_dentro_de_horario,
    validate_inicio,
    validate_modalidad,
    validate_no_en_pasado,
    validate_nota,
)
from app.repositories.agenda_repository import AgendaRepository
from app.services.solicitud_service import SolicitudService

# Roles heredados que hoy escriben leads (mismos que la bandeja web).
_AGENDA_WRITE_ROLES = frozenset({"tester", "advisor", "coordinator", "operations", "admin"})
# Solo Coordinador y Socios marcan realizada / no asistio (seccion 4 del diseño).
_ATTENDANCE_ROLES = frozenset({"coordinator", "ceo", "cto"})


class AgendaService:
    """Servicio de la agenda de reuniones."""

    def __init__(
        self,
        repository: AgendaRepository | None = None,
        solicitudes: SolicitudService | None = None,
    ) -> None:
        self.repository = repository or AgendaRepository()
        self.solicitudes = solicitudes or SolicitudService()

    # ------------------------------------------------------------------ permisos

    def can_agendar(self, actor: AuthenticatedUser | None) -> bool:
        if actor is None:
            return False
        return is_superuser(actor.role) or actor.role in _AGENDA_WRITE_ROLES

    def can_mark_attendance(self, actor: AuthenticatedUser | None) -> bool:
        if actor is None:
            return False
        return actor.role in _ATTENDANCE_ROLES

    # ------------------------------------------------------------------ alcance

    def _mutation_scope(self, actor: AuthenticatedUser) -> UUID | None | bool:
        """Alcance de cartera para una escritura: ``None`` sin restriccion, ``False`` denegar."""
        if not has_portfolio_scope(actor.role):
            return None
        advisor_id = self.solicitudes.resolve_advisor_identity(actor)
        if advisor_id is None:
            return False
        return advisor_id

    def _lead_visible_to(self, user: AuthenticatedUser | None, row: dict[str, Any]) -> bool:
        if user is None:
            return False
        if is_superuser(user.role):
            return True
        if has_portfolio_scope(user.role):
            advisor_id = self.solicitudes.resolve_advisor_identity(user)
            if advisor_id is None:
                return False
            owner = row.get("lead_asesor_id")
            return owner is not None and UUID(str(owner)) == advisor_id
        # Roles sin cartera (executive, readonly, tester, operations, admin): regla actual.
        return True

    # ------------------------------------------------------------------ lectura

    def get_agenda(
        self,
        *,
        desde: Any,
        hasta: Any,
        responsable_id: UUID | None = None,
        user: AuthenticatedUser | None,
    ) -> list[dict[str, Any]]:
        """Citas del calendario con el nombre/id/enlace del lead recortados fuera de alcance."""
        rows = self.repository.list_citas(
            desde, hasta, responsable_id=responsable_id, solo_agendadas=False
        )
        return [self._cita_view(row, user) for row in rows]

    def get_proximas_citas(
        self,
        *,
        desde: Any,
        responsable_id: UUID | None = None,
        user: AuthenticatedUser | None,
    ) -> list[dict[str, Any]]:
        """Proximas reuniones agendadas (vista lista)."""
        rows = self.repository.list_citas(desde, responsable_id=responsable_id, solo_agendadas=True)
        return [self._cita_view(row, user) for row in rows]

    def _cita_view(self, row: dict[str, Any], user: AuthenticatedUser | None) -> dict[str, Any]:
        view: dict[str, Any] = {
            "id_cita": row.get("id_cita"),
            "fecha_hora": self._local(row.get("fecha_hora")),
            "fecha_hora_fin": self._local(row.get("fecha_hora_fin")),
            "agendada_por_nombre": row.get("agendada_por_nombre"),
            "canal": row.get("canal"),
            "estado_cita": row.get("estado_cita"),
            "nota": row.get("nota"),
            "motivo_cancelacion": row.get("motivo_cancelacion"),
            "asesor_nombre": row.get("asesor_nombre"),
            "link_reunion": row.get("link_reunion"),
        }
        if self._lead_visible_to(user, row):
            view["lead_nombre"] = row.get("lead_nombre")
            view["id_lead"] = str(row.get("id_lead"))
            view["lead_fuera_de_alcance"] = False
        else:
            view["lead_nombre"] = None
            view["id_lead"] = None
            view["link_reunion"] = None
            view["nota"] = None
            view["motivo_cancelacion"] = None
            view["lead_fuera_de_alcance"] = True
        return view

    def get_cita_for_lead(self, lead_id: UUID) -> dict[str, Any] | None:
        return self.repository.get_cita_for_lead(lead_id)

    def list_responsables(self) -> list[dict[str, Any]]:
        """Todos los responsables validos (para el filtro del calendario)."""
        return self.repository.get_responsables()

    def get_responsables_para_agendar(
        self, lead_id: UUID, actor: AuthenticatedUser
    ) -> list[dict[str, Any]]:
        """Opciones validas de responsable para el actor (el formulario solo las ofrece)."""
        responsables = self.repository.get_responsables()
        if actor.role == "advisor":
            return [r for r in responsables if r["rol"] == "socio"]
        if actor.role == "coordinator":
            advisor_id = self.solicitudes.resolve_advisor_identity(actor)
            return [
                r
                for r in responsables
                if r["rol"] == "socio"
                or (advisor_id is not None and UUID(str(r["id_asesor"])) == advisor_id)
            ]
        owner = self.repository.lead_active_assignment_owner(lead_id)
        return [
            r
            for r in responsables
            if r["rol"] == "socio" or (owner is not None and UUID(str(r["id_asesor"])) == owner)
        ]

    # ------------------------------------------------------------------ escritura

    def agendar(
        self,
        *,
        lead_id: UUID,
        responsable_id: UUID,
        fecha: str,
        hora: str,
        duracion: int,
        modalidad: str,
        link: str | None,
        nota: str | None,
        actor: AuthenticatedUser,
    ) -> None:
        self._ensure_can_agendar(actor)
        inicio = self._validate_horario(fecha, hora, duracion)
        fin = validate_fin_dentro_de_horario(inicio, duracion)
        modalidad_n = validate_modalidad(modalidad)
        nota_n = validate_nota(nota)
        link_n = self._normalize_link(link)
        advisor_scope = self._require_lead_scope(lead_id, actor)
        responsable = self._resolve_responsable(responsable_id, actor, lead_id)
        self.repository.create_cita(
            lead_id=lead_id,
            responsable_id=UUID(str(responsable["id_asesor"])),
            inicio=inicio,
            fin=fin,
            modalidad=modalidad_n,
            link=link_n,
            nota=nota_n,
            actor=actor,
            advisor_scope=cast(UUID | None, advisor_scope),
        )

    def reagendar(
        self,
        *,
        cita_id: UUID,
        responsable_id: UUID,
        fecha: str,
        hora: str,
        duracion: int,
        modalidad: str,
        link: str | None,
        nota: str | None,
        actor: AuthenticatedUser,
    ) -> None:
        self._ensure_can_agendar(actor)
        inicio = self._validate_horario(fecha, hora, duracion)
        fin = validate_fin_dentro_de_horario(inicio, duracion)
        modalidad_n = validate_modalidad(modalidad)
        nota_n = validate_nota(nota)
        link_n = self._normalize_link(link)
        advisor_scope = self._require_scope(actor)
        cita = self._require_cita(cita_id, actor)
        responsable = self._resolve_responsable(responsable_id, actor, UUID(str(cita["id_lead"])))
        self.repository.update_cita(
            cita_id=cita_id,
            responsable_id=UUID(str(responsable["id_asesor"])),
            inicio=inicio,
            fin=fin,
            modalidad=modalidad_n,
            link=link_n,
            nota=nota_n,
            actor=actor,
            advisor_scope=cast(UUID | None, advisor_scope),
        )

    def cancelar(self, *, cita_id: UUID, motivo: str, actor: AuthenticatedUser) -> None:
        self._ensure_can_agendar(actor)
        motivo_n = " ".join(str(motivo).strip().split())
        if not motivo_n:
            raise AgendaValidationError("El motivo de cancelación es obligatorio")
        advisor_scope = self._require_scope(actor)
        self._require_cita(cita_id, actor)
        self.repository.cancel_cita(
            cita_id=cita_id,
            motivo=motivo_n,
            actor=actor,
            advisor_scope=cast(UUID | None, advisor_scope),
        )

    def marcar_realizada(self, *, cita_id: UUID, actor: AuthenticatedUser) -> None:
        self._ensure_can_mark_attendance(actor)
        advisor_scope = self._require_scope(actor)
        self._require_cita(cita_id, actor)
        self.repository.complete_cita(
            cita_id=cita_id,
            actor=actor,
            advisor_scope=cast(UUID | None, advisor_scope),
        )

    def marcar_no_asistio(self, *, cita_id: UUID, actor: AuthenticatedUser) -> None:
        self._ensure_can_mark_attendance(actor)
        advisor_scope = self._require_scope(actor)
        self._require_cita(cita_id, actor)
        self.repository.no_show_cita(
            cita_id=cita_id,
            actor=actor,
            advisor_scope=cast(UUID | None, advisor_scope),
        )

    # ------------------------------------------------------------------ helpers

    def _ensure_can_agendar(self, actor: AuthenticatedUser) -> None:
        if not isinstance(actor, AuthenticatedUser):
            raise TypeError("actor must be an AuthenticatedUser")
        if not self.can_agendar(actor):
            raise AgendaPermissionError("Esta acción no está disponible para este perfil")

    def _ensure_can_mark_attendance(self, actor: AuthenticatedUser) -> None:
        if not isinstance(actor, AuthenticatedUser):
            raise TypeError("actor must be an AuthenticatedUser")
        if not self.can_mark_attendance(actor):
            raise AgendaPermissionError("Este perfil no puede marcar la asistencia de la reunión")

    def _require_scope(self, actor: AuthenticatedUser) -> UUID | None | bool:
        scope = self._mutation_scope(actor)
        if scope is False:
            raise AgendaNotFoundError("No encontramos el lead solicitado")
        return scope

    def _require_lead_scope(self, lead_id: UUID, actor: AuthenticatedUser) -> UUID | None:
        """Devuelve el alcance de cartera y exige que el lead este dentro de el.

        Se resuelve ANTES de validar el responsable para que un lead fuera de alcance
        responda siempre igual (404) y no se pueda inferir el dueno conociendo su UUID.
        """
        scope = self._mutation_scope(actor)
        if scope is False:
            raise AgendaNotFoundError("No encontramos el lead solicitado")
        if scope is not None and not self.solicitudes.repository.lead_active_assignment_belongs_to(
            lead_id, cast(UUID, scope)
        ):
            raise AgendaNotFoundError("No encontramos el lead solicitado")
        return cast(UUID | None, scope)

    def _validate_horario(self, fecha: str, hora: str, duracion: int) -> Any:
        inicio = validate_inicio(build_agenda_datetime(fecha, hora))
        validate_no_en_pasado(inicio)
        validate_duracion(duracion)
        return inicio

    @staticmethod
    def _normalize_link(link: str | None) -> str | None:
        if link is None:
            return None
        normalized = " ".join(str(link).strip().split())
        return normalized or None

    @staticmethod
    def _local(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.astimezone(AGENDA_TZ)
        return value

    def _resolve_responsable(
        self, responsable_id: UUID, actor: AuthenticatedUser, lead_id: UUID
    ) -> dict[str, Any]:
        responsable = self.repository.get_responsable_by_id(responsable_id)
        if responsable is None:
            raise AgendaValidationError("El responsable seleccionado no es válido")
        if actor.role == "advisor" and responsable["rol"] != "socio":
            raise AgendaPermissionError("El Runner solo puede elegir a un Socio como responsable")
        if responsable["rol"] == "asesor":
            owner = self.repository.lead_active_assignment_owner(lead_id)
            if owner is None or owner != responsable_id:
                raise AgendaValidationError(
                    "Un Coordinador solo es responsable de leads de su propia cartera"
                )
        return responsable

    def _require_cita(self, cita_id: UUID, actor: AuthenticatedUser) -> dict[str, Any]:
        cita = self.repository.get_cita_by_id(cita_id)
        if cita is None:
            raise AgendaNotFoundError("No encontramos la reunión solicitada")
        lead_id = UUID(str(cita["id_lead"]))
        self._require_lead_scope(lead_id, actor)
        return cita
