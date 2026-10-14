"""Regresión del motor contra el fixture de 435 casos reales del portal (AC-5).

Cada caso del fixture se convierte al formato del motor con ``simular_solicitud`` y se
contrasta ``pension_mensual`` con ``PensionMensualEstimada`` del portal: 435/435 dentro de
±1 UF. El motor es el portado desde el paquete de referencia sin cambios numéricos.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.simulador_pension import simular_solicitud

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "casos_portal.json"


@pytest.fixture(scope="module")
def casos() -> list[dict[str, Any]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_tiene_435_casos(casos: list[dict[str, Any]]) -> None:
    assert len(casos) == 435


def test_435_casos_dentro_de_una_uf(casos: list[dict[str, Any]]) -> None:
    fallos: list[str] = []
    for caso in casos:
        resultado = simular_solicitud(caso["solicitud"])
        esperado = float(caso["respuesta"]["PensionMensualEstimada"])
        if abs(resultado.pension_mensual - esperado) > 1.0 + 1e-9:
            fallos.append(f"{caso['id']}: motor={resultado.pension_mensual} portal={esperado}")
    assert fallos == []
