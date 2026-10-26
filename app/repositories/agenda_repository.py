"""Acceso a datos de la agenda de reuniones (tpi.citas y tpi.asesores).

Responsabilidades:
- Leer responsables (filas activas de tpi.asesores con ``atiende_reuniones = true``).
- Leer la reunion de un lead (la agendada o la ultima) y listar citas para el calendario.
- Escribir la reunion (agendar, reagendar, cancelar, realizada, no asistio) en una sola
  transaccion junto con el cambio de estado del lead y su auditoria.

El cambio de estado del lead reutiliza ``SolicitudRepository._update_lead_status_tx`` (la
misma validacion, el mismo candado y la misma auditoria ``cambio_estado_lead``) para no
abrir un segundo camino de estado. La app jamas borra una reunion (``tpi_app`` no tiene
DELETE sobre ``tpi.citas``): cancelar es un UPDATE a ``estado_cita``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg import sql
from psycopg.errors import ExclusionViolation, UniqueViolation

from app.auth.models import AuthenticatedUser
from app.database.connection import get_db_connection
from app.models.agenda import (
    CITA_ESTADO_AGENDADA,
    CITA_ESTADO_CANCELADA,
    CITA_ESTADO_NO_ASISTIO,
    CITA_ESTADO_REALIZADA,
    AgendaConflictError,
    AgendaNotFoundError,
    AgendaValidationError,
)
from app.models.lead_assignment import ASSIGNMENT_ACTIVE_STATE
from app.repositories.solicitud_repository import SolicitudRepository


class AgendaRepository:
    """Repositorio para las operaciones de la agenda de reuniones."""

    _CITA_SELECT = """
        SELECT
            c.id_cita,
            c.id_lead,
            c.id_asesor,
            c.fecha_hora,
            c.fecha_hora_fin,
            c.agendada_por_subject,
            c.agendada_por_nombre,
            c.canal,
            c.estado_cita,
            c.link_reunion,
            c.nota,
            c.motivo_cancelacion,
            c.created_at,
            c.updated_at,
            ases.nombre AS asesor_nombre,
            ases.rol AS asesor_rol
        FROM tpi.citas c
        INNER JOIN tpi.asesores ases ON ases.id_asesor = c.id_asesor
    """

    @staticmethod
    def get_responsables() -> list[dict[str, Any]]:
        """Responsables validos: filas activas con ``atiende_reuniones = true``."""
        query = """
            SELECT id_asesor, nombre, rol
            FROM tpi.asesores
            WHERE atiende_reuniones = TRUE
              AND estado_disponibilidad = 'activo'
            ORDER BY nombre, id_asesor
        """
        with get_db_connection(operation="agenda.responsables") as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def get_responsable_by_id(id_asesor: UUID) -> dict[str, Any] | None:
        query = """
            SELECT id_asesor, nombre, rol
            FROM tpi.asesores
            WHERE id_asesor = %s
              AND atiende_reuniones = TRUE
              AND estado_disponibilidad = 'activo'
            LIMIT 1
        """
        with get_db_connection(operation="agenda.responsable_by_id") as conn:
            with conn.cursor() as cur:
                cur.execute(query, (str(id_asesor),))
                row = cur.fetchone()
                return dict(row) if row else None

    @staticmethod
    def get_cita_by_id(id_cita: UUID) -> dict[str, Any] | None:
        query = f"""
            {AgendaRepository._CITA_SELECT}
            WHERE c.id_cita = %s
            LIMIT 1
        """
        with get_db_connection(operation="agenda.cita_by_id") as conn:
            with conn.cursor() as cur:
                cur.execute(query, (str(id_cita),))
                row = cur.fetchone()
                return dict(row) if row else None

    @staticmethod
    def get_cita_for_lead(id_lead: UUID) -> dict[str, Any] | None:
        """La reunion agendada del lead o, si no hay, la mas reciente por fecha."""
        query = f"""
            {AgendaRepository._CITA_SELECT}
            WHERE c.id_lead = %s
            ORDER BY (c.estado_cita = %s) DESC, c.fecha_hora DESC, c.id_cita DESC
            LIMIT 1
        """
        with get_db_connection(operation="agenda.cita_for_lead") as conn:
            with conn.cursor() as cur:
                cur.execute(query, (str(id_lead), CITA_ESTADO_AGENDADA))
                row = cur.fetchone()
                return dict(row) if row else None

    @staticmethod
    def list_citas(
        desde: datetime,
        hasta: datetime | None = None,
        *,
        responsable_id: UUID | None = None,
        solo_agendadas: bool = False,
    ) -> list[dict[str, Any]]:
        """Citas del calendario en ``[desde, hasta)`` (sin cota superior si ``hasta`` es None).

        Cada fila incluye ``lead_nombre`` y ``lead_asesor_id`` (el dueno de la asignacion
        activa) para que el servicio recorte el nombre del lead fuera de alcance sin
        enviarlo al navegador (AC-4/AC-6).
        """
        clauses: list[Any] = [sql.SQL("c.fecha_hora >= %s")]
        params: list[Any] = [desde]
        if hasta is not None:
            clauses.append(sql.SQL("c.fecha_hora < %s"))
            params.append(hasta)
        if responsable_id is not None:
            clauses.append(sql.SQL("c.id_asesor = %s"))
            params.append(str(responsable_id))
        if solo_agendadas:
            clauses.append(sql.SQL("c.estado_cita = %s"))
            params.append(CITA_ESTADO_AGENDADA)

        where = sql.SQL(" AND ").join(clauses)
        query = sql.SQL("""
            SELECT
                c.id_cita,
                c.id_lead,
                c.id_asesor,
                c.fecha_hora,
                c.fecha_hora_fin,
                c.agendada_por_subject,
                c.agendada_por_nombre,
                c.canal,
                c.estado_cita,
                c.link_reunion,
                c.nota,
                c.motivo_cancelacion,
                ases.nombre AS asesor_nombre,
                ases.rol AS asesor_rol,
                p.nombre_completo AS lead_nombre,
                ass.id_asesor AS lead_asesor_id
            FROM tpi.citas c
            INNER JOIN tpi.asesores ases ON ases.id_asesor = c.id_asesor
            INNER JOIN tpi.leads l ON l.id_lead = c.id_lead
            INNER JOIN tpi.personas p ON p.id_persona = l.id_persona
            LEFT JOIN LATERAL (
                SELECT a.id_asesor
                FROM tpi.asignaciones a
                WHERE a.id_lead = c.id_lead
                  AND a.estado_asignacion = %s
                ORDER BY a.fecha_asignacion DESC, a.id_asignacion DESC
                LIMIT 1
            ) ass ON TRUE
            WHERE {where}
            ORDER BY c.fecha_hora, c.id_cita
        """).format(where=where)
        with get_db_connection(operation="agenda.list_citas") as conn:
            with conn.cursor() as cur:
                cur.execute(query, (ASSIGNMENT_ACTIVE_STATE, *params))
                return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def lead_active_assignment_owner(id_lead: UUID) -> UUID | None:
        """Id del asesor dueno de la asignacion activa del lead (o ``None``)."""
        query = """
            SELECT id_asesor
            FROM tpi.asignaciones
            WHERE id_lead = %s
              AND estado_asignacion = %s
            ORDER BY fecha_asignacion DESC, id_asignacion DESC
            LIMIT 1
        """
        with get_db_connection(operation="agenda.lead_owner") as conn:
            with conn.cursor() as cur:
                cur.execute(query, (str(id_lead), ASSIGNMENT_ACTIVE_STATE))
                row = cur.fetchone()
                return UUID(str(row["id_asesor"])) if row else None

    @staticmethod
    def _lock_lead(cur: Any, id_lead: UUID) -> dict[str, Any] | None:
        cur.execute(
            """
            SELECT estado_lead, id_persona
            FROM tpi.leads
            WHERE id_lead = %s
            FOR UPDATE
            """,
            (str(id_lead),),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    @staticmethod
    def _lead_owned(cur: Any, id_lead: UUID, advisor_scope: UUID | None) -> bool:
        if advisor_scope is None:
            return True
        cur.execute(
            """
            SELECT 1
            FROM tpi.asignaciones
            WHERE id_lead = %s
              AND estado_asignacion = %s
              AND id_asesor = %s
            LIMIT 1
            """,
            (str(id_lead), ASSIGNMENT_ACTIVE_STATE, str(advisor_scope)),
        )
        return cur.fetchone() is not None

    @staticmethod
    def _lock_cita(cur: Any, id_cita: UUID) -> dict[str, Any] | None:
        cur.execute(
            f"{AgendaRepository._CITA_SELECT} WHERE c.id_cita = %s FOR UPDATE OF c",
            (str(id_cita),),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    @staticmethod
    def _insert_cita_audit(
        cur: Any,
        *,
        accion: str,
        id_cita: UUID,
        id_lead: UUID,
        id_persona: Any,
        responsable_id: UUID | None,
        actor: AuthenticatedUser,
        estado_anterior: str | None,
        estado_nuevo: str,
        fecha_anterior: datetime | None,
        fecha_nueva: datetime | None,
        motivo: str | None = None,
    ) -> None:
        detalle = {
            "actor_subject": actor.subject.strip(),
            "id_cita": str(id_cita),
            "responsable_id": str(responsable_id) if responsable_id is not None else None,
            "estado_anterior": estado_anterior,
            "estado_nuevo": estado_nuevo,
            "fecha_hora_anterior": fecha_anterior.isoformat() if fecha_anterior else None,
            "fecha_hora_nueva": fecha_nueva.isoformat() if fecha_nueva else None,
        }
        if motivo is not None:
            detalle["motivo"] = motivo
        cur.execute(
            """
            INSERT INTO tpi.auditoria
                (id_usuario, id_persona, id_lead, accion, tabla_afectada, detalle)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                None,
                str(id_persona) if id_persona is not None else None,
                str(id_lead),
                accion,
                "tpi.citas",
                json.dumps(detalle),
            ),
        )
        if cur.rowcount != 1:
            raise RuntimeError("No se pudo registrar la auditoria de la reunion")

    @staticmethod
    def _translate_constraint(exc: Exception) -> Exception:
        if isinstance(exc, ExclusionViolation):
            return AgendaConflictError(
                "El responsable ya tiene una reunión que se pisa en ese tramo"
            )
        if isinstance(exc, UniqueViolation):
            return AgendaValidationError("El lead ya tiene una reunión agendada")
        return exc

    @staticmethod
    @contextmanager
    def _agenda_tx(operation: str) -> Iterator[Any]:
        """Transaccion de escritura que conserva los errores de dominio de la agenda.

        Los errores de dominio (``AgendaError``) y las violaciones de restriccion
        traducidas se re-lanzan fuera del contexto de ``get_db_connection`` para que no
        sean re-empaquetados como ``DatabaseAppError``.
        """
        error: Exception | None = None
        try:
            with get_db_connection(operation=operation) as conn:
                try:
                    with conn.cursor() as cur:
                        yield cur
                    conn.commit()
                except ExclusionViolation as exc:
                    conn.rollback()
                    error = AgendaRepository._translate_constraint(exc)
                except UniqueViolation as exc:
                    conn.rollback()
                    error = AgendaRepository._translate_constraint(exc)
                except (AgendaNotFoundError, AgendaValidationError, AgendaConflictError) as exc:
                    conn.rollback()
                    error = exc
                except Exception:
                    conn.rollback()
                    raise
        except Exception:
            if error is None:
                raise
        if error is not None:
            raise error

    def create_cita(
        self,
        *,
        lead_id: UUID,
        responsable_id: UUID,
        inicio: datetime,
        fin: datetime,
        modalidad: str,
        link: str | None,
        nota: str | None,
        actor: AuthenticatedUser,
        advisor_scope: UUID | None = None,
    ) -> None:
        """Agenda una reunion nueva y deja el lead en ``reunion_agendada`` (AC-3)."""
        with self._agenda_tx("agenda.create_cita") as cur:
            lead = self._lock_lead(cur, lead_id)
            if lead is None:
                raise AgendaNotFoundError("No encontramos el lead solicitado")
            if not self._lead_owned(cur, lead_id, advisor_scope):
                raise AgendaNotFoundError("No encontramos el lead solicitado")

            cur.execute(
                """
                INSERT INTO tpi.citas
                    (id_lead, id_asesor, fecha_hora, fecha_hora_fin,
                     agendada_por_subject, agendada_por_nombre, canal,
                     estado_cita, link_reunion, nota)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id_cita
                """,
                (
                    str(lead_id),
                    str(responsable_id),
                    inicio,
                    fin,
                    actor.subject.strip(),
                    actor.display_name.strip(),
                    modalidad,
                    CITA_ESTADO_AGENDADA,
                    link,
                    nota,
                ),
            )
            row = cur.fetchone()
            id_cita = UUID(str(row["id_cita"]))

            ok, _ = SolicitudRepository._update_lead_status_tx(
                cur, lead_id, "reunion_agendada", actor=actor, advisor_scope=advisor_scope
            )
            if not ok:
                raise AgendaNotFoundError("No encontramos el lead solicitado")

            self._insert_cita_audit(
                cur,
                accion="cita_agendada",
                id_cita=id_cita,
                id_lead=lead_id,
                id_persona=lead.get("id_persona"),
                responsable_id=responsable_id,
                actor=actor,
                estado_anterior=None,
                estado_nuevo=CITA_ESTADO_AGENDADA,
                fecha_anterior=None,
                fecha_nueva=inicio,
            )

    def update_cita(
        self,
        *,
        cita_id: UUID,
        responsable_id: UUID,
        inicio: datetime,
        fin: datetime,
        modalidad: str,
        link: str | None,
        nota: str | None,
        actor: AuthenticatedUser,
        advisor_scope: UUID | None = None,
    ) -> None:
        """Reagenda una reunion agendada (misma reunion; el lead sigue en ``reunion_agendada``)."""
        with self._agenda_tx("agenda.update_cita") as cur:
            cita = self._lock_cita(cur, cita_id)
            if cita is None:
                raise AgendaNotFoundError("No encontramos la reunion solicitada")
            if cita["estado_cita"] != CITA_ESTADO_AGENDADA:
                raise AgendaValidationError("Solo se puede reagendar una reunión agendada")

            lead_id = UUID(str(cita["id_lead"]))
            lead = self._lock_lead(cur, lead_id)
            if lead is None or not self._lead_owned(cur, lead_id, advisor_scope):
                raise AgendaNotFoundError("No encontramos el lead solicitado")

            fecha_anterior = cita["fecha_hora"]
            cur.execute(
                """
                UPDATE tpi.citas
                SET id_asesor = %s,
                    fecha_hora = %s,
                    fecha_hora_fin = %s,
                    canal = %s,
                    link_reunion = %s,
                    nota = %s,
                    updated_at = NOW()
                WHERE id_cita = %s
                """,
                (
                    str(responsable_id),
                    inicio,
                    fin,
                    modalidad,
                    link,
                    nota,
                    str(cita_id),
                ),
            )
            if cur.rowcount != 1:
                raise AgendaNotFoundError("No encontramos la reunion solicitada")

            ok, _ = SolicitudRepository._update_lead_status_tx(
                cur, lead_id, "reunion_agendada", actor=actor, advisor_scope=advisor_scope
            )
            if not ok:
                raise AgendaNotFoundError("No encontramos el lead solicitado")

            self._insert_cita_audit(
                cur,
                accion="cita_reagendada",
                id_cita=cita_id,
                id_lead=lead_id,
                id_persona=lead.get("id_persona"),
                responsable_id=responsable_id,
                actor=actor,
                estado_anterior=CITA_ESTADO_AGENDADA,
                estado_nuevo=CITA_ESTADO_AGENDADA,
                fecha_anterior=fecha_anterior,
                fecha_nueva=inicio,
            )

    def cancel_cita(
        self,
        *,
        cita_id: UUID,
        motivo: str,
        actor: AuthenticatedUser,
        advisor_scope: UUID | None = None,
    ) -> None:
        """Cancela una reunion agendada con motivo y devuelve el lead a ``en_seguimiento``."""
        with self._agenda_tx("agenda.cancel_cita") as cur:
            cita = self._lock_cita(cur, cita_id)
            if cita is None:
                raise AgendaNotFoundError("No encontramos la reunion solicitada")
            if cita["estado_cita"] != CITA_ESTADO_AGENDADA:
                raise AgendaValidationError("Solo se puede cancelar una reunión agendada")

            lead_id = UUID(str(cita["id_lead"]))
            lead = self._lock_lead(cur, lead_id)
            if lead is None or not self._lead_owned(cur, lead_id, advisor_scope):
                raise AgendaNotFoundError("No encontramos el lead solicitado")

            cur.execute(
                """
                UPDATE tpi.citas
                SET estado_cita = %s,
                    motivo_cancelacion = %s,
                    updated_at = NOW()
                WHERE id_cita = %s
                """,
                (CITA_ESTADO_CANCELADA, motivo, str(cita_id)),
            )
            if cur.rowcount != 1:
                raise AgendaNotFoundError("No encontramos la reunion solicitada")

            ok, _ = SolicitudRepository._update_lead_status_tx(
                cur, lead_id, "en_seguimiento", actor=actor, advisor_scope=advisor_scope
            )
            if not ok:
                raise AgendaNotFoundError("No encontramos el lead solicitado")

            self._insert_cita_audit(
                cur,
                accion="cita_cancelada",
                id_cita=cita_id,
                id_lead=lead_id,
                id_persona=lead.get("id_persona"),
                responsable_id=UUID(str(cita["id_asesor"])),
                actor=actor,
                estado_anterior=CITA_ESTADO_AGENDADA,
                estado_nuevo=CITA_ESTADO_CANCELADA,
                fecha_anterior=cita["fecha_hora"],
                fecha_nueva=None,
                motivo=motivo,
            )

    def complete_cita(
        self,
        *,
        cita_id: UUID,
        actor: AuthenticatedUser,
        advisor_scope: UUID | None = None,
    ) -> None:
        """Marca una reunion como realizada y el lead como ``reunion_realizada``."""
        self._set_cita_outcome(
            cita_id=cita_id,
            estado_cita=CITA_ESTADO_REALIZADA,
            estado_lead="reunion_realizada",
            accion="cita_realizada",
            actor=actor,
            advisor_scope=advisor_scope,
        )

    def no_show_cita(
        self,
        *,
        cita_id: UUID,
        actor: AuthenticatedUser,
        advisor_scope: UUID | None = None,
    ) -> None:
        """Marca una reunion como no asistida y devuelve el lead a ``en_seguimiento``."""
        self._set_cita_outcome(
            cita_id=cita_id,
            estado_cita=CITA_ESTADO_NO_ASISTIO,
            estado_lead="en_seguimiento",
            accion="cita_no_asistio",
            actor=actor,
            advisor_scope=advisor_scope,
        )

    def _set_cita_outcome(
        self,
        *,
        cita_id: UUID,
        estado_cita: str,
        estado_lead: str,
        accion: str,
        actor: AuthenticatedUser,
        advisor_scope: UUID | None = None,
    ) -> None:
        with self._agenda_tx("agenda.set_cita_outcome") as cur:
            cita = self._lock_cita(cur, cita_id)
            if cita is None:
                raise AgendaNotFoundError("No encontramos la reunion solicitada")
            if cita["estado_cita"] != CITA_ESTADO_AGENDADA:
                raise AgendaValidationError(
                    "Una reunión realizada, cancelada o no asistida no se reabre"
                )

            lead_id = UUID(str(cita["id_lead"]))
            lead = self._lock_lead(cur, lead_id)
            if lead is None or not self._lead_owned(cur, lead_id, advisor_scope):
                raise AgendaNotFoundError("No encontramos el lead solicitado")

            cur.execute(
                """
                UPDATE tpi.citas
                SET estado_cita = %s,
                    updated_at = NOW()
                WHERE id_cita = %s
                """,
                (estado_cita, str(cita_id)),
            )
            if cur.rowcount != 1:
                raise AgendaNotFoundError("No encontramos la reunion solicitada")

            ok, _ = SolicitudRepository._update_lead_status_tx(
                cur, lead_id, estado_lead, actor=actor, advisor_scope=advisor_scope
            )
            if not ok:
                raise AgendaNotFoundError("No encontramos el lead solicitado")

            self._insert_cita_audit(
                cur,
                accion=accion,
                id_cita=cita_id,
                id_lead=lead_id,
                id_persona=lead.get("id_persona"),
                responsable_id=UUID(str(cita["id_asesor"])),
                actor=actor,
                estado_anterior=CITA_ESTADO_AGENDADA,
                estado_nuevo=estado_cita,
                fecha_anterior=cita["fecha_hora"],
                fecha_nueva=None,
            )
