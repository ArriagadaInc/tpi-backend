"""Evidencia de entradas y resultado del simulador (SIM-EVIDENCIA-ENTRADAS, AC-1..AC-3).

Verifica, sin base de datos, que el ``detalle`` versionado guarda las entradas y el resultado
con claves estables, sin PII directa, y que las entradas guardadas bastan para reproducir el
resultado y el código de verificación.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.services.simulador_auditoria import build_detalle
from app.services.simulador_service import codigo_verificacion
from app.simulador_pension import Hijo, Persona
from app.simulador_pension import simular as simular_motor


def _kwargs_desde_detalle(detalle: dict[str, Any]) -> dict[str, Any]:
    """Reconstruye los kwargs del motor desde un detalle (sin nombres ni identificadores)."""
    entradas = detalle["entradas"]
    conyuge: Persona | None = None
    hijos: list[Hijo] = []
    for b in entradas["beneficiarios"]:
        if b["parentesco"] == "conyuge":
            conyuge = Persona(b["sexo"], date.fromisoformat(b["fecha_nacimiento"]))
        elif b["parentesco"] == "hijo":
            hijos.append(
                Hijo(
                    sexo=b["sexo"],
                    nacimiento=date.fromisoformat(b["fecha_nacimiento"]),
                    comun=b["comun"],
                    invalidez=b["invalidez"],
                )
            )
    return {
        "fecha_simulacion": date.fromisoformat(entradas["fecha_simulacion"]),
        "saldo_uf": entradas["saldo_uf"],
        "tasa_venta_pct": entradas["tasa_venta_pct"],
        "causante": Persona(
            entradas["causante"]["sexo"],
            date.fromisoformat(entradas["causante"]["fecha_nacimiento"]),
        ),
        "conyuge": conyuge,
        "hijos": tuple(hijos),
        "meses_garantizados": entradas["meses_garantizados"],
        "meses_aumento_temporal": entradas["meses_aumento_temporal"],
        "porcentaje_aumento_temporal": entradas["pct_aumento_temporal"],
        "anios_diferidos": entradas["anios_diferidos"],
        "porcentaje_rvd": entradas["porcentaje_rvd"],
    }


def _detalle_para(
    entradas: dict[str, Any],
    *,
    tipo_escenario: str,
    valor_uf: float | None = None,
) -> dict[str, Any]:
    """Construye el detalle a partir de entradas con la nomenclatura del motor."""
    resultado = simular_motor(**entradas)
    codigo = codigo_verificacion(**entradas)
    return build_detalle(
        actor_subject="subject-executive",
        role="executive",
        tipo_escenario=tipo_escenario,
        version_modelo="1.0.0",
        codigo_verificacion=codigo,
        resultado=resultado,
        fecha_simulacion=entradas["fecha_simulacion"],
        saldo_uf=entradas["saldo_uf"],
        tasa_venta_pct=entradas["tasa_venta_pct"],
        valor_uf=valor_uf,
        meses_garantizados=entradas["meses_garantizados"],
        meses_aumento_temporal=entradas["meses_aumento_temporal"],
        pct_aumento_temporal=entradas["porcentaje_aumento_temporal"],
        anios_diferidos=entradas["anios_diferidos"],
        porcentaje_rvd=entradas["porcentaje_rvd"],
        causante=entradas["causante"],
        conyuge=entradas["conyuge"],
        hijos=entradas["hijos"],
    )


def test_renta_temporal_reproduce_resultado_y_codigo() -> None:
    entradas: dict[str, Any] = {
        "fecha_simulacion": date(2026, 10, 16),
        "saldo_uf": 2000.0,
        "tasa_venta_pct": 5.0,
        "meses_garantizados": 0,
        "meses_aumento_temporal": 0,
        "porcentaje_aumento_temporal": 0.0,
        "anios_diferidos": 5,
        "porcentaje_rvd": 50.0,
        "causante": Persona("H", date(1960, 1, 15)),
        "conyuge": None,
        "hijos": (),
    }
    detalle = _detalle_para(entradas, tipo_escenario="renta_temporal_rvd", valor_uf=38000.0)

    assert detalle["entradas"]["anios_diferidos"] == 5
    assert detalle["resultado"]["meses_diferidos"] > 0
    assert detalle["resultado"]["renta_temporal_uf"] is not None

    reconstruido = simular_motor(**_kwargs_desde_detalle(detalle))
    codigo2 = codigo_verificacion(**_kwargs_desde_detalle(detalle))

    assert reconstruido.pension_mensual == detalle["resultado"]["pension_uf"]
    assert reconstruido.renta_temporal_mensual == detalle["resultado"]["renta_temporal_uf"]
    assert reconstruido.meses_diferidos == detalle["resultado"]["meses_diferidos"]
    assert codigo2 == detalle["codigo_verificacion"]


def test_familia_reproduce_resultado_y_codigo() -> None:
    entradas: dict[str, Any] = {
        "fecha_simulacion": date(2026, 10, 16),
        "saldo_uf": 3000.0,
        "tasa_venta_pct": 4.7,
        "meses_garantizados": 120,
        "meses_aumento_temporal": 24,
        "porcentaje_aumento_temporal": 10.0,
        "anios_diferidos": 0,
        "porcentaje_rvd": 100.0,
        "causante": Persona("H", date(1960, 1, 15)),
        "conyuge": Persona("M", date(1962, 5, 20)),
        "hijos": (
            Hijo("M", date(2000, 3, 10), comun=True, invalidez="no"),
            Hijo("H", date(1998, 7, 1), comun=False, invalidez="parcial"),
        ),
    }
    detalle = _detalle_para(entradas, tipo_escenario="renta_inmediata_familia")

    beneficiarios = detalle["entradas"]["beneficiarios"]
    parentescos = [b["parentesco"] for b in beneficiarios]
    assert parentescos == ["conyuge", "hijo", "hijo"]
    assert detalle["resultado"]["renta_temporal_uf"] is None
    assert detalle["resultado"]["meses_diferidos"] == 0

    reconstruido = simular_motor(**_kwargs_desde_detalle(detalle))
    codigo2 = codigo_verificacion(**_kwargs_desde_detalle(detalle))

    assert reconstruido.pension_mensual == detalle["resultado"]["pension_uf"]
    assert codigo2 == detalle["codigo_verificacion"]


def test_detalle_pequeno_y_versionado() -> None:
    entradas: dict[str, Any] = {
        "fecha_simulacion": date(2026, 10, 16),
        "saldo_uf": 3000.0,
        "tasa_venta_pct": 4.7,
        "meses_garantizados": 0,
        "meses_aumento_temporal": 0,
        "porcentaje_aumento_temporal": 0.0,
        "anios_diferidos": 0,
        "porcentaje_rvd": 100.0,
        "causante": Persona("H", date(1960, 1, 15)),
        "conyuge": None,
        "hijos": (),
    }
    detalle = _detalle_para(entradas, tipo_escenario="renta_inmediata_causante")

    assert detalle["schema_version"] == 1
    assert len(json.dumps(detalle, ensure_ascii=False)) < 4096
