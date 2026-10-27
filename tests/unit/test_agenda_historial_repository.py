"""Unit tests for the agenda-history repository read path (AC-1).

The application never reads ``tpi.auditoria`` nor ``tpi.citas`` directly for the
lead timeline: the only read model is the sanitized view ``tpi.v_historial_agenda``
(migration 011), joined with ``tpi.asesores`` for the responsible name and ordered
by ``fecha_hora DESC, id_auditoria DESC``.
"""

from __future__ import annotations

import inspect

from app.repositories.agenda_repository import AgendaRepository


def _source() -> str:
    return inspect.getsource(AgendaRepository.get_lead_agenda_events)


def test_get_lead_agenda_events_reads_only_the_sanitized_view() -> None:
    source = _source()
    assert "FROM tpi.v_historial_agenda" in source
    # Nunca lee la tabla de auditoria ni la de citas como fuente de la linea de tiempo.
    assert "FROM tpi.auditoria" not in source
    assert "FROM tpi.citas" not in source


def test_get_lead_agenda_events_joins_asesores_for_responsible_name() -> None:
    source = _source()
    assert "LEFT JOIN tpi.asesores" in source
    assert "responsable_nombre" in source


def test_get_lead_agenda_events_uses_the_stable_order() -> None:
    source = _source()
    assert "ORDER BY v.fecha_hora DESC, v.id_auditoria DESC" in source
