"""Unit tests for the H3.3.4 three-source timeline merge (presentation layer)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.web.presentation import (
    FollowUpNote,
    build_timeline_items,
    state_history_cutover_notice,
)

_TZ = ZoneInfo("America/Santiago")


def _event(fecha_hora: datetime | None, *, actor: str = "user-001") -> dict:
    return {
        "id_auditoria": "11111111-1111-1111-1111-111111111111",
        "id_lead": "22222222-2222-2222-2222-222222222222",
        "fecha_hora": fecha_hora,
        "actor_subject": actor,
        "id_asesor": "33333333-3333-3333-3333-333333333333",
        "asesor_nombre": "Asesor Demo",
        "estado_anterior": "nuevo",
        "estado_nuevo": "asignado",
    }


def _state_change(fecha_hora: datetime | None, *, actor: str = "user-002") -> dict:
    return {
        "id_auditoria": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "id_lead": "22222222-2222-2222-2222-222222222222",
        "fecha_hora": fecha_hora,
        "actor_subject": actor,
        "estado_anterior": "contactado",
        "estado_nuevo": "cerrado",
    }


def _note(timestamp: str, author: str = "Alvaro", text: str = "Nota") -> FollowUpNote:
    return FollowUpNote(timestamp=timestamp, author=author, text=text)


def test_merges_three_sources_chronologically() -> None:
    items = build_timeline_items(
        [_event(datetime(2026, 9, 5, 10, 0, tzinfo=_TZ))],
        [_note("05/09/2026 11:00")],
        [_state_change(datetime(2026, 9, 5, 12, 0, tzinfo=_TZ))],
    )

    assert [item["kind"] for item in items] == ["state_change", "note", "event"]
    assert items[0]["display_time"] == "05/09/2026 12:00"
    assert items[1]["display_time"] == "05/09/2026 11:00"
    assert items[2]["display_time"] == "05/09/2026 10:00"


def test_state_change_item_exposes_actor_and_delta() -> None:
    items = build_timeline_items(
        [],
        [],
        [_state_change(datetime(2026, 9, 5, 12, 0, tzinfo=_TZ), actor="user-002")],
    )

    assert len(items) == 1
    item = items[0]
    assert item["kind"] == "state_change"
    assert item["actor"] == "user-002"
    assert item["estado_anterior"] == "contactado"
    assert item["estado_nuevo"] == "cerrado"


def test_deterministic_tiebreak_event_then_state_change_then_note() -> None:
    moment = datetime(2026, 9, 5, 10, 0, tzinfo=_TZ)
    items = build_timeline_items(
        [_event(moment)],
        [_note("05/09/2026 10:00")],
        [_state_change(moment)],
    )

    assert [item["kind"] for item in items] == ["event", "state_change", "note"]


def test_state_change_timestamp_is_displayed_in_america_santiago() -> None:
    utc_time = datetime(2026, 8, 5, 14, 30, tzinfo=UTC)
    items = build_timeline_items([], [], [_state_change(utc_time)])

    expected = utc_time.astimezone(_TZ).strftime("%d/%m/%Y %H:%M")
    assert items[0]["display_time"] == expected
    assert items[0]["timestamp"].tzinfo is not None


def test_state_change_without_timestamp_is_skipped() -> None:
    items = build_timeline_items([], [_note("05/09/2026 10:00")], [_state_change(None)])

    assert [item["kind"] for item in items] == ["note"]


def test_backward_compatible_with_two_argument_callers() -> None:
    items = build_timeline_items(
        [_event(datetime(2026, 9, 5, 10, 0, tzinfo=_TZ))],
        [_note("05/09/2026 11:00")],
    )
    assert [item["kind"] for item in items] == ["note", "event"]


def test_state_change_items_have_no_edit_or_delete_controls() -> None:
    items = build_timeline_items([], [], [_state_change(datetime(2026, 9, 5, 12, 0, tzinfo=_TZ))])
    item = items[0]
    for forbidden in ("edit", "delete", "delete_url", "edit_url"):
        assert forbidden not in item


def test_cutover_notice_uses_configured_date() -> None:
    notice = state_history_cutover_notice(date(2026, 9, 20))
    assert "20/09/2026" in notice
    assert "migracion 008" in notice
    assert "asignaciones anteriores se conservan" in notice


def test_cutover_notice_never_invents_a_date_when_unconfigured() -> None:
    notice = state_history_cutover_notice(None)
    assert "20/09/2026" not in notice
    assert "migracion 008" in notice
    assert "asignaciones anteriores se conservan" in notice


def test_cutover_settings_default_has_no_fake_date() -> None:
    settings = Settings(_env_file=None)
    assert settings.lead_state_history_cutover is None


def test_cutover_settings_parses_valid_iso_date() -> None:
    settings = Settings(_env_file=None, LEAD_STATE_HISTORY_CUTOVER="2026-09-20")
    assert settings.lead_state_history_cutover == date(2026, 9, 20)


def test_cutover_settings_rejects_invalid_or_timezone_values() -> None:
    # The field is a plain date (timezone-agnostic): malformed dates and any
    # datetime/timezone-bearing value fail explicitly instead of producing a
    # misleading coverage date.
    for bad in (
        "not-a-date",
        "20/09/2026",
        "2026-13-40",
        "2026-9-20",
        "2026-09-20T10:00:00Z",
        "2026-09-20 10:00",
        "",
    ):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, LEAD_STATE_HISTORY_CUTOVER=bad)
