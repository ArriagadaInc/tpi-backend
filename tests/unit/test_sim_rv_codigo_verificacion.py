"""Código de verificación determinístico (AC-12)."""

from __future__ import annotations

from datetime import date

from app.services.simulador_service import codigo_verificacion
from app.simulador_pension import Hijo, Persona


def _codigo(**kwargs: object) -> str:
    base: dict[str, object] = {
        "fecha_simulacion": date(2026, 10, 1),
        "saldo_uf": 3000.0,
        "tasa_venta_pct": 4.7,
        "causante": Persona("H", date(1960, 1, 1)),
        "conyuge": None,
        "hijos": (),
        "meses_garantizados": 0,
        "meses_aumento_temporal": 0,
        "porcentaje_aumento_temporal": 0.0,
        "anios_diferidos": 0,
        "porcentaje_rvd": 100.0,
    }
    base.update(kwargs)
    return codigo_verificacion(**base)  # type: ignore[arg-type]


def test_formato_12_hex() -> None:
    codigo = _codigo()
    assert len(codigo) == 12
    int(codigo, 16)  # no lanza si es hexadecimal


def test_deterministico() -> None:
    assert _codigo() == _codigo()


def test_depende_de_las_entradas() -> None:
    assert _codigo(saldo_uf=3000.0) != _codigo(saldo_uf=4000.0)
    assert _codigo(fecha_simulacion=date(2026, 10, 1)) != _codigo(
        fecha_simulacion=date(2026, 10, 2)
    )


def test_conyuge_e_hijos_alteran_el_codigo() -> None:
    con_conyuge = _codigo(conyuge=Persona("M", date(1962, 1, 1)))
    con_hijo = _codigo(hijos=(Hijo("H", date(2010, 1, 1), comun=True),))
    assert con_conyuge != _codigo()
    assert con_hijo != _codigo()
