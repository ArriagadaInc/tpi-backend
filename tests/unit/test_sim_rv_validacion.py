"""Validación del borde y del servicio (AC-4, AC-13): rangos, edades y rechazos de escenario."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.services.simulador_service import (
    SimulacionInvalidaError,
    SimuladorService,
    validar_edades,
)
from app.simulador_pension import Hijo, Persona
from app.web.routes.simulador import SimuladorForm


def _form(**kwargs: object) -> SimuladorForm:
    defaults: dict[str, object] = {"saldo_uf": 3000, "tasa_venta_pct": 4.7}
    defaults.update(kwargs)
    return SimuladorForm(**defaults)


def test_form_acepta_caso_minimo() -> None:
    form = _form()
    assert form.saldo_uf == 3000
    assert form.hijos == []


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("saldo_uf", 0),
        ("saldo_uf", 499),
        ("saldo_uf", 100_001),
        ("tasa_venta_pct", 0.4),
        ("tasa_venta_pct", 8.1),
        ("meses_garantizados", -1),
        ("meses_garantizados", 481),
        ("meses_aumento_temporal", -1),
        ("meses_aumento_temporal", 601),
        ("porcentaje_aumento_temporal", -1),
        ("porcentaje_aumento_temporal", 101),
        ("anios_diferidos", -1),
        ("anios_diferidos", 11),
        ("porcentaje_rvd", 40),
        ("porcentaje_rvd", 49),
    ],
)
def test_form_rechaza_rangos_invalidos(campo: str, valor: float) -> None:
    with pytest.raises(ValidationError):
        _form(**{campo: valor})


def test_form_rechaza_mas_de_4_hijos() -> None:
    hijos = [{"sexo": "H", "nacimiento": date(2010, 1, 1)} for _ in range(5)]
    with pytest.raises(ValidationError):
        SimuladorForm(saldo_uf=3000, tasa_venta_pct=4.7, hijos=hijos)


def test_validar_edades_rechaza_causante_fuera_de_rango() -> None:
    causante = Persona("H", date(1990, 1, 1))  # 36 años en la fecha de simulación
    with pytest.raises(SimulacionInvalidaError):
        validar_edades(
            fecha_simulacion=date(2026, 10, 1),
            causante=causante,
            conyuge=None,
            hijos=(),
            anios_diferidos=0,
        )


def test_validar_edades_acepta_causante_dentro_de_rango() -> None:
    causante = Persona("H", date(1960, 1, 1))  # 66 años
    validar_edades(
        fecha_simulacion=date(2026, 10, 1),
        causante=causante,
        conyuge=None,
        hijos=(),
        anios_diferidos=0,
    )


def test_simular_rechaza_renta_temporal_con_conyuge() -> None:
    service = SimuladorService()
    with pytest.raises(SimulacionInvalidaError):
        service.simular(
            fecha_simulacion=date(2026, 10, 1),
            saldo_uf=3000,
            tasa_venta_pct=4.7,
            causante=Persona("H", date(1960, 1, 1)),
            conyuge=Persona("M", date(1962, 1, 1)),
            hijos=(),
            meses_garantizados=0,
            meses_aumento_temporal=0,
            porcentaje_aumento_temporal=0.0,
            anios_diferidos=3,
            porcentaje_rvd=100.0,
        )


def test_simular_renta_inmediata_causante_solo() -> None:
    service = SimuladorService()
    resultado = service.simular(
        fecha_simulacion=date(2026, 10, 1),
        saldo_uf=3000,
        tasa_venta_pct=4.7,
        causante=Persona("H", date(1960, 1, 1)),
        conyuge=None,
        hijos=(),
        meses_garantizados=0,
        meses_aumento_temporal=0,
        porcentaje_aumento_temporal=0.0,
        anios_diferidos=0,
        porcentaje_rvd=100.0,
    )
    assert resultado.pension_mensual > 0


def test_simular_rechaza_hijo_con_invalidez_invalida() -> None:
    service = SimuladorService()
    # invalidez "invalido" no es uno de los valores válidos (no/parcial/total).
    with pytest.raises(SimulacionInvalidaError):
        service.simular(
            fecha_simulacion=date(2026, 10, 1),
            saldo_uf=3000,
            tasa_venta_pct=4.7,
            causante=Persona("H", date(1962, 1, 1)),
            conyuge=Persona("M", date(1964, 1, 1)),
            hijos=(Hijo("H", date(2010, 1, 1), comun=True, invalidez="invalido"),),
            meses_garantizados=0,
            meses_aumento_temporal=0,
            porcentaje_aumento_temporal=0.0,
            anios_diferidos=0,
            porcentaje_rvd=100.0,
        )
