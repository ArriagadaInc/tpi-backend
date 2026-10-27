"""Unit tests for the agenda-event merge in ``build_timeline_items`` (AC-2).

The agenda events (migration 011) join the timeline as ``kind='agenda'`` items with
America/Santiago timestamps, the meeting date resolved from ``fecha_hora_nueva``
falling back to ``fecha_hora_anterior``, and a deterministic place in the fixed
source rank (event < simulation < state_change < agenda < note).
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.web.presentation import FollowUpNote, build_timeline_items

_TZ = ZoneInfo("America/Santiago")


def _agenda(
    fecha_hora: datetime | None,
    *,
    accion: str = "cita_agendada",
    actor: str = "subject-ceo",
    responsable: str | None = "Socio A",
    fecha_hora_anterior: datetime | None = None,
    fecha_hora_nueva: datetime | None = None,
) -> dict:
    return {
        "id_auditoria": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "id_lead": "22222222-2222-2222-2222-222222222222",
        "fecha_hora": fecha_hora,
        "accion": accion,
        "actor_subject": actor,
        "id_cita": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "responsable_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
        "responsable_nombre": responsable,
        "fecha_hora_anterior": fecha_hora_anterior,
        "fecha_hora_nueva": fecha_hora_nueva,
    }


def _note(timestamp: str, author: str = "Alvaro", text: str = "Nota") -> FollowUpNote:
    return FollowUpNote(timestamp=timestamp, author=author, text=text)


def _state_change(fecha_hora: datetime | None) -> dict:
    return {
        "id_auditoria": "dddddddd-dddd-dddd-dddd-dddddddddddd",
        "id_lead": "22222222-2222-2222-2222-222222222222",
        "fecha_hora": fecha_hora,
        "actor_subject": "subject-coord",
        "estado_anterior": "en_seguimiento",
        "estado_nuevo": "cerrado",
    }


def test_agenda_event_normalizes_fields_and_meeting_date() -> None:
    momento = datetime(2026, 9, 5, 10, 0, tzinfo=_TZ)
    items = build_timeline_items(
        [],
        [],
        [],
        [],
        [_agenda(momento, fecha_hora_nueva=datetime(2026, 9, 6, 11, 30, tzinfo=_TZ))],
    )
    assert len(items) == 1
    item = items[0]
    assert item["kind"] == "agenda"
    assert item["timestamp"] == momento
    assert item["display_time"] == "05/09/2026 10:00"
    assert item["actor"] == "subject-ceo"
    assert item["accion"] == "cita_agendada"
    assert item["responsable"] == "Socio A"
    assert item["fecha_reunion"] == "06/09/2026 11:30"
    assert item["fecha_anterior"] is None


def test_agenda_meeting_date_falls_back_to_anterior_when_nueva_is_missing() -> None:
    momento = datetime(2026, 9, 5, 10, 0, tzinfo=_TZ)
    items = build_timeline_items(
        [],
        [],
        [],
        [],
        [
            _agenda(
                momento,
                accion="cita_cancelada",
                fecha_hora_anterior=datetime(2026, 9, 4, 9, 0, tzinfo=_TZ),
                fecha_hora_nueva=None,
            )
        ],
    )
    assert items[0]["fecha_reunion"] == "04/09/2026 09:00"
    assert items[0]["fecha_anterior"] == "04/09/2026 09:00"


def test_reagendada_carries_previous_and_new_dates() -> None:
    momento = datetime(2026, 9, 5, 10, 0, tzinfo=_TZ)
    items = build_timeline_items(
        [],
        [],
        [],
        [],
        [
            _agenda(
                momento,
                accion="cita_reagendada",
                fecha_hora_anterior=datetime(2026, 9, 5, 9, 0, tzinfo=_TZ),
                fecha_hora_nueva=datetime(2026, 9, 6, 11, 0, tzinfo=_TZ),
            )
        ],
    )
    assert items[0]["fecha_anterior"] == "05/09/2026 09:00"
    assert items[0]["fecha_reunion"] == "06/09/2026 11:00"


def test_agenda_timestamp_is_displayed_in_america_santiago() -> None:
    utc_time = datetime(2026, 8, 5, 14, 30, tzinfo=UTC)
    items = build_timeline_items([], [], [], [], [_agenda(utc_time, fecha_hora_nueva=utc_time)])
    expected = utc_time.astimezone(_TZ).strftime("%d/%m/%Y %H:%M")
    assert items[0]["display_time"] == expected


def test_agenda_event_without_timestamp_is_skipped() -> None:
    items = build_timeline_items([], [], [], [], [_agenda(None)])
    assert items == []


def test_agenda_sorts_between_state_change_and_note_on_exact_tie() -> None:
    momento = datetime(2026, 9, 5, 10, 0, tzinfo=_TZ)
    items = build_timeline_items(
        [],
        [_note("05/09/2026 10:00")],
        [_state_change(momento)],
        [],
        [_agenda(momento, fecha_hora_nueva=momento)],
    )
    assert [item["kind"] for item in items] == ["state_change", "agenda", "note"]


def test_agenda_mixes_chronologically_with_notes() -> None:
    items = build_timeline_items(
        [],
        [_note("05/09/2026 11:00")],
        [],
        [],
        [
            _agenda(
                datetime(2026, 9, 5, 12, 0, tzinfo=_TZ),
                fecha_hora_nueva=datetime(2026, 9, 5, 12, 0, tzinfo=_TZ),
            ),
            _agenda(
                datetime(2026, 9, 5, 9, 0, tzinfo=_TZ),
                fecha_hora_nueva=datetime(2026, 9, 5, 9, 0, tzinfo=_TZ),
            ),
        ],
    )
    assert [item["kind"] for item in items] == ["agenda", "note", "agenda"]
