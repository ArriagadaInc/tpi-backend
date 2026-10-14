"""Generación del PDF efímero (AC-7, AC-8, AC-9)."""

from __future__ import annotations

from datetime import datetime

from app.services.simulador_service import Escenario, _esc, generar_pdf
from app.simulador_pension import Resultado


def _resultado() -> Resultado:
    return Resultado(
        pension_mensual=150.25,
        pension_exacta=150.25,
        prima_uf=3000.0,
        prima_neta_afp_uf=0.0,
        cnu=20.0,
    )


def _pdf(**kwargs: object) -> bytes:
    base: dict[str, object] = {
        "fecha_hora": datetime(2026, 10, 14, 12, 0, 0),
        "ejecutivo": "Ejecutivo Demo",
        "lead_nombre": "Juan Perez",
        "escenario": Escenario("renta_inmediata_causante", "Renta vitalicia inmediata (causante)"),
        "parametros": [("Saldo en UF", "3.000,00"), ("Tasa de venta", "4,70%")],
        "resultado": _resultado(),
        "tasa_venta_pct": 4.7,
        "valor_uf": None,
        "advertencia_ventana": False,
        "codigo": "0123456789ab",
    }
    base.update(kwargs)
    return generar_pdf(**base)  # type: ignore[arg-type]


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
    pdf = _pdf()
    assert b"/URI" not in pdf
    assert b"/JavaScript" not in pdf


def test_pdf_con_valor_uf_muestra_equivalente() -> None:
    pdf = _pdf(valor_uf=37000.0)
    assert pdf.startswith(b"%PDF")
