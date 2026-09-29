"""Unit tests for the H3.3.3 timeline merge helper (presentation layer)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.web.presentation import FollowUpNote, build_timeline_items

_TZ = ZoneInfo("America/Santiago")


def _event(
    fecha_hora: datetime | None,
    *,
    actor: str = "user-001",
    asesor_nombre: str | None = "Asesor Demo",
    estado_anterior: str = "nuevo",
    estado_nuevo: str = "asignado",
) -> dict:
    return {
        "id_auditoria": "11111111-1111-1111-1111-111111111111",
        "id_lead": "22222222-2222-2222-2222-222222222222",
        "fecha_hora": fecha_hora,
        "actor_subject": actor,
        "id_asesor": "33333333-3333-3333-3333-333333333333",
        "asesor_nombre": asesor_nombre,
        "estado_anterior": estado_anterior,
        "estado_nuevo": estado_nuevo,
    }


def _note(timestamp: str, author: str = "Alvaro", text: str = "Nota") -> FollowUpNote:
    return FollowUpNote(timestamp=timestamp, author=author, text=text)


def test_build_timeline_items_returns_empty_for_no_events_or_notes() -> None:
    assert build_timeline_items([], []) == []


def test_build_timeline_items_sorts_descending_by_timestamp() -> None:
    items = build_timeline_items(
        [
            _event(datetime(2026, 9, 5, 10, 0, tzinfo=_TZ)),
            _event(datetime(2026, 9, 5, 12, 0, tzinfo=_TZ)),
        ],
        [_note("05/09/2026 11:00")],
    )

    assert [item["kind"] for item in items] == ["event", "note", "event"]
    assert items[0]["display_time"] == "05/09/2026 12:00"
    assert items[1]["display_time"] == "05/09/2026 11:00"
    assert items[2]["display_time"] == "05/09/2026 10:00"


def test_build_timeline_items_keeps_event_before_note_on_exact_tie() -> None:
    items = build_timeline_items(
        [_event(datetime(2026, 9, 5, 10, 0, tzinfo=_TZ))],
        [_note("05/09/2026 10:00")],
    )

    assert [item["kind"] for item in items] == ["event", "note"]


def test_event_timestamp_is_displayed_in_america_santiago() -> None:
    utc_time = datetime(2026, 8, 5, 14, 30, tzinfo=UTC)
    items = build_timeline_items([_event(utc_time)], [])

    expected = utc_time.astimezone(_TZ).strftime("%d/%m/%Y %H:%M")
    assert items[0]["display_time"] == expected
    assert items[0]["timestamp"].tzinfo is not None


def test_event_without_timestamp_is_skipped() -> None:
    items = build_timeline_items([_event(None)], [_note("05/09/2026 10:00")])

    assert [item["kind"] for item in items] == ["note"]


def test_note_timestamp_is_parsed_as_aware_santiago_datetime() -> None:
    items = build_timeline_items([], [_note("05/09/2026 10:00")])

    assert items[0]["timestamp"] == datetime(2026, 9, 5, 10, 0, tzinfo=_TZ)
    assert items[0]["display_time"] == "05/09/2026 10:00"


def test_malformed_note_timestamp_falls_back_safely() -> None:
    items = build_timeline_items([], [_note("not-a-date")])

    assert items[0]["display_time"] == "not-a-date"
    assert items[0]["timestamp"].tzinfo is not None
