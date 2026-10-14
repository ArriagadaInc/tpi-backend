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


# --- Rangos validados por escenario (revisión R1-MAJOR-1) ---------------------


@pytest.mark.parametrize("saldo", [999, 800, 500])
def test_form_rechaza_saldo_insuficiente_en_renta_temporal(saldo: float) -> None:
    with pytest.raises(ValidationError):
        _form(saldo_uf=saldo, anios_diferidos=3)


def test_form_acepta_saldo_minimo_renta_temporal() -> None:
    assert _form(saldo_uf=1000, anios_diferidos=3).saldo_uf == 1000


def test_form_acepta_saldo_500_renta_inmediata() -> None:
    assert _form(saldo_uf=500, anios_diferidos=0).saldo_uf == 500


@pytest.mark.parametrize("tasa", [7.6, 8.0])
def test_form_rechaza_tasa_alta_en_renta_inmediata(tasa: float) -> None:
    with pytest.raises(ValidationError):
        _form(tasa_venta_pct=tasa, anios_diferidos=0)


def test_form_acepta_tasa_7_5_renta_inmediata() -> None:
    assert _form(tasa_venta_pct=7.5, anios_diferidos=0).tasa_venta_pct == 7.5


def test_form_acepta_tasa_8_renta_temporal() -> None:
    assert _form(tasa_venta_pct=8.0, anios_diferidos=3).tasa_venta_pct == 8.0


# --- Valor UF finito y con tope (revisión R1-MINOR-1) -------------------------


@pytest.mark.parametrize("valor", [float("inf"), float("-inf"), float("nan"), 0.0, -1.0])
def test_form_rechaza_valor_uf_no_finito_o_no_positivo(valor: float) -> None:
    with pytest.raises(ValidationError):
        _form(valor_uf=valor)


def test_form_rechaza_valor_uf_sobre_tope() -> None:
    with pytest.raises(ValidationError):
        _form(valor_uf=1_000_001)


def test_form_acepta_valor_uf_razonable() -> None:
    assert _form(valor_uf=37000.0).valor_uf == 37000.0


# --- Relación RVD/RT entera (revisión R1-MINOR-2) -----------------------------


@pytest.mark.parametrize("rvd", [50.5, 51.5, 75.5, 99.5, 50.1])
def test_form_rechaza_rvd_fraccionario(rvd: float) -> None:
    with pytest.raises(ValidationError):
        _form(porcentaje_rvd=rvd)


@pytest.mark.parametrize("rvd", [100.0, 50.0, 51.0, 99.0, 75.0])
def test_form_acepta_rvd_valido(rvd: float) -> None:
    assert _form(porcentaje_rvd=rvd).porcentaje_rvd == rvd


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
