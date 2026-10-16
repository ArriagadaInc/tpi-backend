"""Ficha PDF «Estudio de pensión» (SIM-FICHA-PDF): estructura, cálculos derivados y conservación.

La ficha es carta apaisada (792 × 612 pt) con banda azul marino, fila de datos, tablas de
OPCIÓN I/II con Rescate Total, pie de contacto y banda inferior con logo. Se conservan de
SIM-RV-V1: la leyenda referencial, la versión del modelo, el código de verificación, el escape de
marcado, los metadatos genéricos sin PII y la ausencia de enlaces/scripts/adjuntos. Las pruebas
inspeccionan el contenido descomprimiendo los flujos (ASCII85+Flate) con la librería estándar.
"""

from __future__ import annotations

import base64
import re
import zlib
from datetime import date, datetime

import pytest

from app.services.simulador_service import (
    Escenario,
    _anios,
    _clp,
    _esc,
    _pension_aumentada,
    _rescate_opcion_i,
    _rescate_opcion_ii,
    _tratamiento,
    _uf,
    _valor_actual,
    _valor_futuro,
    generar_pdf,
)
from app.simulador_pension import Resultado


def _resultado(pension: float = 150.25, **kwargs: object) -> Resultado:
    base: dict[str, object] = {
        "pension_mensual": pension,
        "pension_exacta": pension,
        "prima_uf": 3000.0,
        "prima_neta_afp_uf": 0.0,
        "cnu": 20.0,
    }
    base.update(kwargs)
    return Resultado(**base)  # type: ignore[arg-type]


def _pdf(**kwargs: object) -> bytes:
    base: dict[str, object] = {
        "fecha_hora": datetime(2026, 10, 14, 12, 0, 0),
        "ejecutivo": "Ejecutivo Demo",
        "lead_nombre": "Juan Perez",
        "sexo_causante": "H",
        "causante_nacimiento": date(1960, 1, 15),
        "tiene_conyuge": False,
        "escenario": Escenario("renta_inmediata_causante", "Renta vitalicia inmediata (causante)"),
        "resultado": _resultado(),
        "tasa_venta_pct": 4.7,
        "valor_uf": None,
        "saldo_uf": 3000.0,
        "meses_garantizados": 0,
        "meses_aumento_temporal": 0,
        "porcentaje_aumento_temporal": 0.0,
        "anios_diferidos": 0,
        "codigo": "0123456789ab",
    }
    base.update(kwargs)
    return generar_pdf(**base)  # type: ignore[arg-type]


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


# --- PDF válido y conservación de SIM-RV-V1 (AC-4) ------------------------------


def test_pdf_valido() -> None:
    pdf = _pdf()
    assert pdf.startswith(b"%PDF")
    assert pdf.rstrip().endswith(b"%%EOF")


def test_escape_de_marcado() -> None:
    assert _esc("<script>&") == "&lt;script&gt;&amp;"


def test_nombre_adversarial_no_rompe_el_pdf() -> None:
    # Un nombre con <, > y & no debe romper ni alterar la generación (AC-8).
    pdf = _pdf(lead_nombre="Juan <Pérez> & Cía")
    assert pdf.startswith(b"%PDF")
    assert pdf.rstrip().endswith(b"%%EOF")


def test_pdf_no_contiene_enlaces_ni_scripts() -> None:
    pdf = _pdf(valor_uf=37000.0)
    assert b"/URI" not in pdf
    assert b"/JavaScript" not in pdf
    assert b"/EmbeddedFile" not in pdf
    assert b"/Annots" not in pdf
    assert b"/AA" not in pdf


def test_pdf_es_carta_apaisada() -> None:
    pdf = _pdf()
    assert b"MediaBox [ 0 0 792 612 ]" in pdf


def test_leyenda_version_y_codigo_conservados() -> None:
    texto = _texto_pdf(_pdf())
    assert b"Estimaci" in texto  # "Estimación referencial no vinculante"
    assert b"0123456789ab" in texto
    assert b"Documento referencial no vinculante" in texto


# --- Cálculos derivados (AC-2) ----------------------------------------------------


def test_rescate_total_opcion_i() -> None:
    assert _rescate_opcion_i(10.0, 120) == pytest.approx(1200.0)
    assert _rescate_opcion_i(10.0, 0) == pytest.approx(0.0)


def test_valor_actual() -> None:
    assert _valor_actual(10.0, 20000.0) == pytest.approx(200000.0)
    assert _valor_actual(10.0, None) is None


def test_valor_futuro() -> None:
    # Ejemplo de la especificación: 400.000 × 1,04³ ≈ 449.946.
    assert _valor_futuro(400000.0, 36) == pytest.approx(400000.0 * 1.04**3)


def test_rescate_total_opcion_ii() -> None:
    # 20×36 + 10×(240−36) = 2.760,00 UF (ejemplo de la especificación).
    assert _rescate_opcion_ii(10.0, 100.0, 36, 240) == pytest.approx(2760.0)


def test_pension_aumentada() -> None:
    assert _pension_aumentada(10.0, 100.0) == pytest.approx(20.0)
    assert _pension_aumentada(10.0, 0.0) == pytest.approx(10.0)


# --- Formato es-CL y tratamiento ---------------------------------------------------


def test_formato_es_cl() -> None:
    assert _uf(10.0) == "10,00"
    assert _uf(1200.0) == "1.200,00"
    assert _clp(370000.0) == "370.000"


def test_tratamiento_y_anios() -> None:
    assert _tratamiento("H") == "Sr."
    assert _tratamiento("M") == "Sra."
    assert _anios(120) == "10"
    assert _anios(6) == "0,5"


# --- Estructura de la ficha (AC-1, AC-3) ------------------------------------------


def test_ficha_opcion_i_simple() -> None:
    texto = _texto_pdf(_pdf(resultado=_resultado(pension=10.0), valor_uf=37000.0))
    assert b"ESTUDIO DE PENSI" in texto
    assert b"FECHA DE NAC: 1960/01/15" in texto
    assert b"Renta Vitalicia Inmediata" in texto
    assert b"Rescate Total" in texto
    assert b"Capital: 3.000,00 UF" in texto
    assert b"T: 4,70%" in texto
    assert b"Simple" in texto
    assert b"10,00" in texto
    assert b"370.000" in texto
    assert b">>>>" in texto
    assert b"0,00" in texto  # rescate total sin garantía
    assert b"Esta Opci" in texto  # "Esta Opción es vitalicia sin recálculo"
    assert b"Aumento Temporal de Pensi" not in texto


def test_ficha_opcion_i_periodo_garantizado() -> None:
    texto = _texto_pdf(
        _pdf(resultado=_resultado(pension=10.0), valor_uf=37000.0, meses_garantizados=120)
    )
    assert b"Periodo Garantizado" in texto
    assert b"10 a" in texto  # 10 años (120 meses / 12)
    assert b"1.200,00" in texto  # rescate: 10 × 120


def test_ficha_opcion_ii_con_aumento_temporal() -> None:
    # Ejemplo de la especificación: base 10 UF, aumento 100% durante 36 meses, garantía 240 meses.
    texto = _texto_pdf(
        _pdf(
            resultado=_resultado(pension=10.0),
            valor_uf=20000.0,
            meses_garantizados=240,
            meses_aumento_temporal=36,
            porcentaje_aumento_temporal=100.0,
        )
    )
    assert b"Aumento Temporal de Pensi" in texto
    assert b"Sin Excedente" in texto
    assert b"Inflaci" in texto  # "Inflación Futura 4%"
    assert b"20,00" in texto  # pensión aumentada
    assert b"400.000" in texto  # $ Valor Actual de la pensión aumentada
    assert b"449.946" in texto  # $ Valor Futuro (400.000 × 1,04³)
    assert b"2.760,00" in texto  # rescate Opción II
    assert b"200.000" in texto  # $ Valor Actual de la base


def test_ficha_pie_y_contacto() -> None:
    texto = _texto_pdf(_pdf(ejecutivo="Ejecutiva Demo", sexo_causante="M"))
    assert b"Ejecutiva Demo" in texto
    assert b"Tu Pensi" in texto  # "Tu Pensión Inteligente"
    assert b"contacto@tupensioninteligente.cl" in texto
    assert b"www.tupensioninteligente.cl" in texto
    assert b"Dr. Sotero del R" in texto  # dirección corporativa
    assert b"Sra." in texto  # tratamiento femenino


def test_ficha_renta_temporal_rvd_conserva_seccion() -> None:
    resultado = _resultado(pension=150.25, renta_temporal_mensual=120.5, meses_diferidos=60)
    texto = _texto_pdf(
        _pdf(
            resultado=resultado,
            escenario=Escenario("renta_temporal_rvd", "Renta temporal + RVD"),
            anios_diferidos=5,
            valor_uf=37000.0,
        )
    )
    assert b"RENTA TEMPORAL" in texto
    assert b"Meses de diferimiento" in texto
    assert b"Renta temporal mensual" in texto
    assert b"150,25" in texto
    assert b"120,50" in texto
    assert b"60" in texto
    assert b"Renta Vitalicia Inmediata" not in texto  # Opción I no aplica en RVD
