"""Pruebas de las marcas de adjuntos y su interpretación en las notas (AC-5)."""

from __future__ import annotations

from uuid import UUID

from app.attachments.marks import (
    build_attachment_mark,
    match_full_attachment_mark,
    neutralize_attachment_marks,
    parse_attachment_marks,
    strip_attachment_marks,
)
from app.web.presentation import parse_lead_comments

PDF_ID = UUID("11111111-1111-1111-1111-111111111111")
PNG_ID = UUID("22222222-2222-2222-2222-222222222222")


def test_build_attachment_mark_uses_canonical_format() -> None:
    assert build_attachment_mark("pdf", PDF_ID) == f"[adjunto:pdf:{PDF_ID}]"


def test_parse_attachment_marks_finds_valid_marks_in_order() -> None:
    text = (
        f"Nota con [adjunto:pdf:{PDF_ID}] y [adjunto:png:{PNG_ID}] "
        "[adjunto:gif:00000000-0000-0000-0000-000000000000]"
    )
    marks = parse_attachment_marks(text)
    assert [mark.attachment_id for mark in marks] == [PDF_ID, PNG_ID]
    assert [mark.attachment_type for mark in marks] == ["pdf", "png"]


def test_strip_attachment_marks_removes_only_valid_marks() -> None:
    text = f"hola [adjunto:pdf:{PDF_ID}] mundo [corchetes]"
    assert strip_attachment_marks(text) == "hola  mundo [corchetes]"


def test_match_full_attachment_mark_only_matches_complete_line() -> None:
    assert match_full_attachment_mark(f"[adjunto:pdf:{PDF_ID}]").attachment_id == PDF_ID
    assert match_full_attachment_mark(f"hola [adjunto:pdf:{PDF_ID}]") is None
    assert match_full_attachment_mark("texto normal") is None


def test_neutralize_attachment_marks_breaks_the_prefix() -> None:
    original = f"mira [adjunto:pdf:{PDF_ID}]"
    neutralized = neutralize_attachment_marks(original)
    assert neutralized == f"mira [adjunto&#58;pdf:{PDF_ID}]"
    assert parse_attachment_marks(neutralized) == []


def test_note_with_marks_parses_text_and_attachments() -> None:
    raw = (
        "Solicitud original.\n\n"
        "[23/08/2026 22:32] Alvaro Local\n"
        "Cliente contactado.\n"
        f"[adjunto:pdf:{PDF_ID}]\n"
        f"[adjunto:png:{PNG_ID}]"
    )
    parsed = parse_lead_comments(raw)
    assert parsed.original_request == "Solicitud original."
    assert len(parsed.notes) == 1
    note = parsed.notes[0]
    assert note.text == "Cliente contactado."
    assert [mark.attachment_id for mark in note.attachments] == [PDF_ID, PNG_ID]
    assert [mark.attachment_type for mark in note.attachments] == ["pdf", "png"]


def test_hand_written_mark_inline_is_not_an_attachment() -> None:
    raw = (
        "Solicitud original.\n\n"
        "[23/08/2026 22:32] Alvaro Local\n"
        f"Nota con [adjunto:pdf:{PDF_ID}] en el texto"
    )
    parsed = parse_lead_comments(raw)
    note = parsed.notes[0]
    assert note.attachments == ()
    assert str(PDF_ID) not in note.text


def test_original_request_marks_are_stripped() -> None:
    raw = f"Solicitud [adjunto:pdf:{PDF_ID}] original."
    parsed = parse_lead_comments(raw)
    assert parsed.original_request == "Solicitud  original."
