"""Pruebas de los límites conocidos de los adjuntos (CRM-ADJUNTOS-REVISION-PREPROD).

Fijan el comportamiento actual SIN cambiarlo, construidas en memoria (sin archivos
binarios en el repositorio ni dependencias nuevas). Cada prueba apunta a la sección
del informe ``docs/ADJUNTOS_REVISION_PREPROD.md`` que documenta el límite.
"""

from __future__ import annotations

import struct
import zlib

from app.attachments.validation import validate_attachment_content


def _pack_rationals(triple: tuple[int, int, int]) -> bytes:
    """Empaqueta tres racionales (numerador, denominador=1) en little-endian."""
    out = bytearray()
    for value in triple:
        out += struct.pack("<II", value, 1)
    return bytes(out)


def _jpeg_with_exif_gps(width: int = 2, height: int = 3) -> bytes:
    """JPEG válido con un bloque EXIF APP1 que incluye coordenadas GPS.

    La estructura EXIF es un TIFF little-endian con IFD0 apuntando a un IFD de
    GPS (GPSLatitudeRef/GPSLatitude y GPSLongitudeRef/GPSLongitude).
    """
    lat = (33, 26, 58)  # grados, minutos, segundos
    lon = (70, 40, 12)
    lat_ref = b"N\x00"
    lon_ref = b"W\x00"

    # Cabecera TIFF little-endian (magic 42) con IFD0 en el offset 8.
    tiff = bytearray(b"II" + struct.pack("<H", 42) + struct.pack("<I", 8))

    # IFD0: una sola entrada, el puntero GPSInfo (tag 0x8825, LONG, count 1).
    gps_ifd_offset = 8 + 2 + 12 + 4  # 26
    tiff += struct.pack("<H", 1)
    tiff += struct.pack("<HHI", 0x8825, 4, 1) + struct.pack("<I", gps_ifd_offset)
    tiff += struct.pack("<I", 0)

    # IFD de GPS: 4 entradas. Las racionales se guardan después del IFD.
    lat_rationals_offset = gps_ifd_offset + 2 + 4 * 12 + 4  # 80
    lon_rationals_offset = lat_rationals_offset + 24  # 104

    tiff += struct.pack("<H", 4)
    tiff += struct.pack("<HHI", 0x0001, 2, 2) + lat_ref + b"\x00\x00"  # GPSLatitudeRef
    tiff += struct.pack("<HHI", 0x0002, 5, 3) + struct.pack("<I", lat_rationals_offset)
    tiff += struct.pack("<HHI", 0x0003, 2, 2) + lon_ref + b"\x00\x00"  # GPSLongitudeRef
    tiff += struct.pack("<HHI", 0x0004, 5, 3) + struct.pack("<I", lon_rationals_offset)
    tiff += struct.pack("<I", 0)
    tiff += _pack_rationals(lat)
    tiff += _pack_rationals(lon)

    exif_payload = b"Exif\x00\x00" + bytes(tiff)
    app1 = b"\xff\xe1" + struct.pack(">H", len(exif_payload) + 2) + exif_payload

    # SOF0 con dimensiones (mismo formato que las pruebas de validación).
    sof_payload = (
        struct.pack(">B", 8) + struct.pack(">HH", height, width) + b"\x01" + b"\x01\x11\x00"
    )
    sof = b"\xff\xc0" + struct.pack(">H", 2 + len(sof_payload)) + sof_payload

    return b"\xff\xd8" + app1 + sof + b"\xff\xd9"


def _pdf_with_javascript_in_flate_object_stream() -> bytes:
    """PDF cuyo JavaScript vive dentro de un object stream comprimido con FlateDecode.

    La validación actual busca los tokens prohibidos en los bytes crudos del PDF
    y no descomprime los streams, así que este PDF pasa hoy la validación
    (límite del punto 6 del informe).
    """
    objetos = b"<< /S /JavaScript /JS (app.alert(1)) >>"
    comprimido = zlib.compress(objetos)
    stream = (
        b"<< /Type /ObjStm /N 1 /First 4 /Filter /FlateDecode /Length "
        + str(len(comprimido)).encode()
        + b" >>\nstream\n"
        + comprimido
        + b"\nendstream"
    )
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n" + stream + b"\nendobj\n"
        b"2 0 obj\n<< /Type /Catalog >>\nendobj\n"
        b"xref\n0 3\n0000000000 65535 f \n"
        b"trailer\n<< /Size 3 /Root 2 0 R >>\n"
        b"%%EOF"
    )


def test_current_behavior_jpeg_with_exif_gps_is_accepted_and_bytes_preserved() -> None:
    """Límite del punto 3 (EXIF y GPS) de docs/ADJUNTOS_REVISION_PREPROD.md.

    Un JPEG con EXIF que incluye coordenadas GPS se acepta y sus bytes no se
    modifican (no hay re-codificación en esta primera versión).
    """
    jpeg = _jpeg_with_exif_gps()
    assert b"Exif\x00\x00" in jpeg

    result = validate_attachment_content(jpeg)

    assert result.attachment_type == "jpg"
    assert result.content == jpeg  # los bytes se conservan tal cual


def test_known_limitation_javascript_inside_flate_object_stream_passes() -> None:
    """Límite del punto 6 (validación de PDF) de docs/ADJUNTOS_REVISION_PREPROD.md.

    La validación busca los tokens prohibidos en los bytes crudos del PDF y no
    descomprime los streams: un PDF cuyo ``/JavaScript`` está dentro de un object
    stream comprimido con FlateDecode pasa hoy la validación.
    """
    pdf = _pdf_with_javascript_in_flate_object_stream()

    # El token no queda visible en crudo: va dentro del stream comprimido.
    assert b"/JavaScript" not in pdf
    assert b"/JS" not in pdf

    result = validate_attachment_content(pdf)

    assert result.attachment_type == "pdf"
