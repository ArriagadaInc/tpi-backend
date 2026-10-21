"""Pruebas de validación por contenido de adjuntos (AC-2 y AC-9)."""

from __future__ import annotations

import struct

import pytest

from app.attachments.validation import (
    MAX_ATTACHMENT_BYTES,
    MAX_IMAGE_PIXELS,
    AttachmentValidationError,
    validate_attachment_content,
)


def _png(width: int = 1, height: int = 1) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00"
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + b"\x00\x00\x00\x00"
    iend = struct.pack(">I", 0) + b"IEND" + b"\x00\x00\x00\x00"
    return signature + ihdr + iend


def _jpeg(width: int = 1, height: int = 1) -> bytes:
    sof_payload = (
        struct.pack(">B", 8) + struct.pack(">HH", height, width) + b"\x01" + b"\x01\x11\x00"
    )
    segment = struct.pack(">H", 2 + len(sof_payload)) + sof_payload
    return b"\xff\xd8" + b"\xff\xc0" + segment + b"\xff\xd9"


def _pdf(*, inject: bytes | None = None) -> bytes:
    if inject is not None:
        return b"%PDF-1.4\n1 0 obj\n<<" + inject + b">>\nendobj\n%%EOF"
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"


def _code(content: bytes) -> str:
    with pytest.raises(AttachmentValidationError) as excinfo:
        validate_attachment_content(content)
    return excinfo.value.code


def test_valid_png_returns_type_size_and_sha256() -> None:
    content = _png(width=2, height=3)
    result = validate_attachment_content(content)
    assert result.attachment_type == "png"
    assert result.size == len(content)
    assert len(result.sha256) == 64
    assert result.content == content


def test_valid_jpeg_returns_jpg_type() -> None:
    assert validate_attachment_content(_jpeg(4, 5)).attachment_type == "jpg"


def test_valid_pdf_returns_pdf_type() -> None:
    assert validate_attachment_content(_pdf()).attachment_type == "pdf"


def test_empty_file_is_rejected() -> None:
    assert _code(b"") == "empty_file"


def test_file_over_10_mib_is_rejected() -> None:
    assert _code(b"x" * (MAX_ATTACHMENT_BYTES + 1)) == "too_large"


def test_png_with_valid_signature_but_truncated_is_rejected() -> None:
    truncated = _png()[:-12]  # sin IEND
    assert _code(truncated) == "invalid_content"


def test_png_with_wrong_ihdr_length_is_rejected() -> None:
    content = bytearray(_png())
    content[8:12] = struct.pack(">I", 14)
    assert _code(bytes(content)) == "invalid_content"


def test_png_with_pixel_bomb_dimensions_is_rejected() -> None:
    assert _code(_png(width=10000, height=6000)) == "too_many_pixels"


def test_jpeg_without_sof_marker_is_rejected() -> None:
    assert _code(b"\xff\xd8\xff\xd9") == "invalid_content"


def test_jpeg_with_pixel_bomb_dimensions_is_rejected() -> None:
    assert _code(_jpeg(width=10000, height=6000)) == "too_many_pixels"


@pytest.mark.parametrize(
    "token", [b"/JS", b"/JavaScript", b"/Launch", b"/EmbeddedFile", b"/Encrypt"]
)
def test_pdf_with_forbidden_token_is_rejected(token: bytes) -> None:
    assert _code(_pdf(inject=token)) == "unsafe_pdf"


def test_pdf_name_escape_js_is_rejected() -> None:
    # "/J#53" decodifica a "/JS" (0x53 = 'S').
    assert _code(_pdf(inject=b"/J#53")) == "unsafe_pdf"


def test_pdf_without_eof_is_rejected() -> None:
    assert _code(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj") == "invalid_content"


@pytest.mark.parametrize(
    "content",
    [
        b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
        b"<!doctype html><html></html>",
        b"GIF89a\x00\x00\x00\x00\x00",
        b"II*\x00\x08\x00\x00\x00\x00\x00\x00\x00",  # TIFF little-endian
        b"RIFF\x00\x00\x00\x00WEBPVP8 ",
        b"MZ\x90\x00",  # ejecutable
        b"P6\n1 1\n255\n",  # PPM
        b"%!PS-Adobe",  # EPS
    ],
)
def test_unsupported_types_are_rejected(content: bytes) -> None:
    assert _code(content) == "unsupported_type"


def test_content_decides_not_declared_type() -> None:
    # PNG disfrazado de PDF y PDF disfrazado de PNG: decide el contenido.
    assert validate_attachment_content(_png()).attachment_type == "png"
    assert validate_attachment_content(_pdf()).attachment_type == "pdf"


def test_dimension_limit_is_enforced_before_accepting() -> None:
    # Un pixel por encima del tope se rechaza aunque la firma sea válida.
    width = MAX_IMAGE_PIXELS + 1
    assert _code(_png(width=width, height=1)) == "too_many_pixels"
