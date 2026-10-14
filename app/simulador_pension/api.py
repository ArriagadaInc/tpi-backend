"""Función pública `simular`: valida la entrada y delega en el motor de renta inmediata o de renta temporal + RVD."""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from datetime import date

from . import renta_diferida, renta_inmediata
from .modelos import Hijo, Persona, Resultado
from .mortalidad import edad_en_meses

TIPOS_PENSION = ("vejez_edad", "vejez_anticipada")
# Rangos realmente cubiertos por las 435 simulaciones del portal (ver docs/SIM_RV_V1_PENDIENTES.md, sección 1).
VENTANA_VALIDADA = (date(2025, 10, 15), date(2026, 10, 13))
EDADES_VALIDADAS = (
    59,
    100,
)  # causante: individual 60–100, con cónyuge 60–92, con hijos 62–92, RT 59–88
MAX_HIJOS_VALIDADOS = 4


class NoValidadoError(NotImplementedError):
    """La combinación pedida existe en el portal pero no fue reconstruida o validada."""


def _validar_persona(p: Persona, rol: str) -> None:
    if p.sexo not in ("H", "M"):
        raise ValueError(f"{rol}: sexo debe ser 'H' o 'M'")
    if not isinstance(p.nacimiento, date):
        raise ValueError(f"{rol}: nacimiento debe ser datetime.date")


def simular(
    *,
    fecha_simulacion: date,
    saldo_uf: float,
    tasa_venta_pct: float,
    causante: Persona,
    conyuge: Persona | None = None,
    hijos: Sequence[Hijo] = (),
    meses_garantizados: int = 0,
    meses_aumento_temporal: int = 0,
    porcentaje_aumento_temporal: float = 0.0,
    anios_diferidos: int = 0,
    porcentaje_rvd: float = 100.0,
    valor_nominal_bono: float = 0.0,
    tipo_pension: str = "vejez_edad",
) -> Resultado:
    """Pensión mensual de renta vitalicia (inmediata o diferida con renta temporal) en UF.

    tasa_venta_pct: tasa de venta anual en % (p. ej. 4.7). El portal usa una tasa automática por tipo de pensión que
        cambia con el tiempo; aquí debe darse explícitamente.
    porcentaje_aumento_temporal: % del aumento (p. ej. 50 = +50% durante `meses_aumento_temporal`).
    porcentaje_rvd: relación RVD/RT en % (100, 50 u "Otro RVD" 51–99); solo con anios_diferidos > 0.
    """
    if tipo_pension not in TIPOS_PENSION:
        raise NoValidadoError(
            f"tipo_pension {tipo_pension!r} no reconstruido (solo {TIPOS_PENSION})"
        )
    if valor_nominal_bono:
        raise NoValidadoError(
            "bono de reconocimiento: el portal devuelve error de servidor para todo bono > 0; "
            "no hay datos para reconstruir su valorización"
        )
    if tipo_pension == "vejez_anticipada":
        warnings.warn(
            "vejez anticipada: solo verificada con un caso de control (mismo resultado que vejez edad)",
            stacklevel=2,
        )
    _validar_persona(causante, "causante")
    if conyuge is not None:
        _validar_persona(conyuge, "cónyuge")
    for k, h in enumerate(hijos, 1):
        _validar_persona(Persona(h.sexo, h.nacimiento), f"hijo {k}")
        if h.invalidez not in ("no", "parcial", "total"):
            raise ValueError(f"hijo {k}: invalidez debe ser 'no', 'parcial' o 'total'")
    if saldo_uf <= 0:
        raise ValueError("saldo_uf debe ser positivo")
    if not 0 < tasa_venta_pct <= 100:
        raise ValueError("tasa_venta_pct debe estar entre 0 y 100 (en %)")
    if meses_garantizados < 0 or meses_aumento_temporal < 0 or anios_diferidos < 0:
        raise ValueError("meses y años no pueden ser negativos")
    if not 0 <= porcentaje_aumento_temporal <= 100:
        raise ValueError("porcentaje_aumento_temporal debe estar entre 0 y 100")

    if not VENTANA_VALIDADA[0] <= fecha_simulacion <= VENTANA_VALIDADA[1]:
        warnings.warn(
            "fecha de simulación fuera de la ventana validada "
            f"({VENTANA_VALIDADA[0].isoformat()} a {VENTANA_VALIDADA[1].isoformat()})",
            stacklevel=2,
        )
    edad = edad_en_meses(causante.nacimiento, fecha_simulacion) // 12
    if not EDADES_VALIDADAS[0] <= edad <= EDADES_VALIDADAS[1]:
        warnings.warn(
            f"edad del causante ({edad}) fuera del rango validado {EDADES_VALIDADAS}", stacklevel=2
        )
    if len(hijos) > MAX_HIJOS_VALIDADOS:
        warnings.warn("más de 4 hijos: no validado contra el portal", stacklevel=2)

    if anios_diferidos > 0:
        if conyuge is not None or hijos or meses_garantizados or meses_aumento_temporal:
            raise NoValidadoError(
                "renta temporal + RVD solo está reconstruida para causante individual, sin garantía ni aumento"
            )
        if not (porcentaje_rvd == 100 or 50 <= porcentaje_rvd < 100):
            raise ValueError("porcentaje_rvd debe ser 100, 50 o un entero entre 51 y 99")
        r = renta_diferida.calcular(
            fecha=fecha_simulacion,
            saldo=saldo_uf,
            tasa_pct=tasa_venta_pct,
            causante=causante,
            anios_diferidos=anios_diferidos,
            relacion_rvd=porcentaje_rvd / 100.0,
        )
        return Resultado(
            pension_mensual=round(r["P"] + 1e-12, 2),
            pension_exacta=r["P"],
            prima_uf=r["prima"],
            prima_neta_afp_uf=saldo_uf - r["prima"],
            cnu=r["cnu"],
            renta_temporal_mensual=r["renta_temporal"],
            comision_uf=r["comision"],
            meses_diferidos=int(r["meses_diferidos"]),
        )

    r = renta_inmediata.calcular(
        fecha=fecha_simulacion,
        saldo=saldo_uf,
        tasa_pct=tasa_venta_pct,
        causante=causante,
        conyuge=conyuge,
        hijos=tuple(hijos),
        meses_garantizados=int(meses_garantizados),
        meses_aumento=int(meses_aumento_temporal),
        aumento=porcentaje_aumento_temporal / 100.0,
    )
    return Resultado(
        pension_mensual=round(r["P"] + 1e-12, 2),
        pension_exacta=r["P"],
        prima_uf=saldo_uf,
        prima_neta_afp_uf=0.0,
        cnu=r["cnu"],
        factor_a=r["A"],
        deduccion_cuota_mortuoria_uf=r["Q"],
    )
