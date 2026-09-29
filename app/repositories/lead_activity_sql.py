"""Single source of truth for the operational-activity SQL of a lead (H3.3.4).

The executive dashboard and the ``/leads`` listing must agree bit for bit on what
"sin asignar" and "estancado" mean: if the alert says 37 unassigned leads, the
listing linked from that alert has to return the same 37 rows. Both definitions
therefore live here and are imported by both repositories instead of being
re-typed in each query.

Human definitions reproduced literally (never reinterpreted here):

- *Movimiento operativo* = human note, assignment event or general state change.
  ``updated_at`` is never a movement. When a lead has no movement at all,
  ``fecha_ingreso`` is the reproducible floor.
- *Estancado* = ``umbral`` complete calendar days without operational movement
  (configurable, default 5). Internal operational rule, not an SLA.

Every fragment is a fixed constant: no value from a filter, a request or the
database is ever interpolated into these strings. Placeholders are documented per
function so callers can pass parameters in the right order.
"""

from __future__ import annotations

from typing import Final

from app.models.lead_assignment import ASSIGNMENT_ACTIVE_STATE

# Server-generated follow-up note header: "[dd/mm/YYYY HH:MM] <author>".
NOTE_TS_PATTERN: Final[str] = r"\[(\d{2}/\d{2}/\d{4} \d{2}:\d{2})\]"

# Session-timezone-independent conversion of the note wall-clock (written in
# America/Santiago) into a TIMESTAMPTZ. ``regexp_replace`` reorders dd/mm/YYYY
# into ISO, casts to a naive timestamp, then interprets it in America/Santiago.
NOTE_TS_EXPR: Final[str] = (
    "(regexp_replace(m[1], '^(\\d{2})/(\\d{2})/(\\d{4}) (\\d{2}):(\\d{2})$', "
    "'\\3-\\2-\\1 \\4:\\5:00'))::timestamp AT TIME ZONE 'America/Santiago'"
)


def ultimo_movimiento_expr(alias: str = "l") -> str:
    """SQL expression for the last operational movement of a lead.

    Contains exactly **one** ``%s`` placeholder: the note-header regex pattern
    (:data:`NOTE_TS_PATTERN`). ``alias`` is the caller's alias for ``tpi.leads``
    and is never taken from user input.
    """
    return f"""
        GREATEST(
            {alias}.fecha_ingreso,
            COALESCE((
                SELECT MAX(a.fecha_asignacion)
                FROM tpi.asignaciones a
                WHERE a.id_lead = {alias}.id_lead
            ), {alias}.fecha_ingreso),
            COALESCE((
                SELECT MAX(v.fecha_hora)
                FROM tpi.v_historial_estado_lead v
                WHERE v.id_lead = {alias}.id_lead
            ), {alias}.fecha_ingreso),
            COALESCE((
                SELECT MAX({NOTE_TS_EXPR})
                FROM regexp_matches({alias}.comentarios, %s, 'g') AS m
            ), {alias}.fecha_ingreso)
        )
    """


def estancado_predicate(alias: str = "l") -> str:
    """Boolean predicate for a stale lead.

    Contains exactly **two** ``%s`` placeholders, in this order: the note-header
    regex pattern and the threshold in calendar days.
    """
    return f"({ultimo_movimiento_expr(alias)}) <= now() - make_interval(days => %s)"


def sin_asignar_predicate(alias: str = "l") -> str:
    """Boolean predicate for a lead without an active assignment.

    Contains exactly **one** ``%s`` placeholder: the active assignment state
    (:data:`~app.models.lead_assignment.ASSIGNMENT_ACTIVE_STATE`).
    """
    return f"""
        NOT EXISTS (
            SELECT 1 FROM tpi.asignaciones a
            WHERE a.id_lead = {alias}.id_lead
              AND a.estado_asignacion = %s
        )
    """


def sin_asignar_params() -> list[str]:
    """Parameters for :func:`sin_asignar_predicate`, in placeholder order."""
    return [ASSIGNMENT_ACTIVE_STATE]


def estancado_params(threshold_days: int) -> list[object]:
    """Parameters for :func:`estancado_predicate`, in placeholder order."""
    return [NOTE_TS_PATTERN, int(threshold_days)]
