"""Ventana abierta y aviso permanente de valores referenciales (SIM-RV-V1-VENTANA).

Por decisión del humano (2026-10-14) la ventana validada del simulador queda abierta: la
generación ya no depende de la fecha (se elimina el estado «bloqueado», el corte de 90 días y el
422 por vencimiento) y, en su lugar, la pantalla y el PDF indican siempre que los resultados son
valores referenciales (no vinculantes). Estas pruebas verifican que cualquier fecha genera el PDF
y que el aviso referencial está presente en el PDF sin la advertencia de ventana vencida.
"""

from __future__ import annotations

import base64
import re
import zlib
from datetime import date, datetime

import pytest

from app.services.simulador_service import Escenario, generar_pdf
from app.simulador_pension import Resultado


def _resultado() -> Resultado:
    return Resultado(
        pension_mensual=150.25,
        pension_exacta=150.25,
        prima_uf=3000.0,
        prima_neta_afp_uf=0.0,
        cnu=20.0,
    )


def _pdf(fecha_hora: datetime) -> bytes:
    return generar_pdf(
        fecha_hora=fecha_hora,
        ejecutivo="Ejecutivo Demo",
        lead_nombre="Juan Perez",
        sexo_causante="H",
        causante_nacimiento=date(1960, 1, 15),
        tiene_conyuge=False,
        escenario=Escenario("renta_inmediata_causante", "Renta vitalicia inmediata (causante)"),
        resultado=_resultado(),
        tasa_venta_pct=4.7,
        valor_uf=None,
        saldo_uf=3000.0,
        meses_garantizados=0,
        meses_aumento_temporal=0,
        porcentaje_aumento_temporal=0.0,
        anios_diferidos=0,
        codigo="0123456789ab",
    )


def _texto_pdf(pdf: bytes) -> bytes:
    """Decodifica los flujos de contenido del PDF (ASCII85+Flate) para inspeccionar el texto."""
    partes: list[bytes] = []
    for raw in re.findall(rb"stream\r?\n(.*?)endstream", pdf, re.DOTALL):
        data = raw.strip(b"\r\n")
        if data.endswith(b"~>"):
            try:
                data = base64.a85decode(data, adobe=True)
            except ValueError:
                continue
        try:
            data = zlib.decompress(data)
        except zlib.error:
            pass
        partes.append(data)
    return b"\n".join(partes)


# --- Cualquier fecha genera (se eliminó el bloqueo por vencimiento) -------------


@pytest.mark.parametrize(
    "fecha",
    [
        datetime(2020, 1, 1, 12, 0),  # mucho antes de la ventana validada original
        datetime(2026, 10, 13, 12, 0),  # último día de la ventana validada original
        datetime(2027, 1, 12, 12, 0),  # primer día que antes se bloqueaba (fin + 90 días)
        datetime(2030, 6, 1, 12, 0),  # mucho después
    ],
)
def test_cualquier_fecha_genera_pdf(fecha: datetime) -> None:
    pdf = _pdf(fecha)
    assert pdf.startswith(b"%PDF")
    assert pdf.rstrip().endswith(b"%%EOF")


# --- Aviso referencial permanente en el PDF (sin advertencia de ventana) ---------


def test_aviso_referencial_siempre_en_pdf() -> None:
    for fecha in (datetime(2026, 10, 13, 12, 0), datetime(2030, 6, 1, 12, 0)):
        texto = _texto_pdf(_pdf(fecha))
        assert b"Supuestos y advertencias" in texto
        assert b"valores referenciales y no vinculantes" in texto
        assert b"ventana de validaci" not in texto
        assert b"vencid" not in texto
