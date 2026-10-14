"""Mortalidad mensual: tablas CMF 2020 con mejoramiento, edad en meses y supervivencia.

Todo es el resultado de la ingeniería inversa del simulador (ver docs/SIM_RV_V1_MODELO.md);
las constantes ``A0_MESES`` y ``C_CALENDARIO`` son ajustes empíricos, no hechos normativos
confirmados.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import cast

import numpy as np

EDAD_MAX = 110
N_MAX_MESES = (EDAD_MAX + 2) * 12
A0_MESES = 1  # la edad en meses se cuenta +1 respecto del cumpleaños efectivo
C_CALENDARIO = (
    -0.4568
)  # años: el mejoramiento corre desde ~mediados de 2020 hasta ~mediados de cada mes
_RUTA = Path(__file__).resolve().parent / "datos" / "tablas_mortalidad.npz"

TIPOS_TABLA = ("vejez", "sobrev", "inval")


@lru_cache(maxsize=1)
def _datos() -> dict[str, np.ndarray]:
    return cast(dict[str, np.ndarray], dict(np.load(_RUTA)))


def tabla(sexo: str, tipo: str) -> tuple[np.ndarray, np.ndarray]:
    """(q2020[edad], aa[edad, año-2021]).

    tipo 'vejez': H = CB-H-2020, M = RV-M-2020 (causante).
    tipo 'sobrev': H = CB-2020, M = B-2020 (cónyuge e hijos no inválidos).
    tipo 'inval': MI-2020 (hijos inválidos).
    """
    if tipo not in TIPOS_TABLA:
        raise ValueError(f"tipo de tabla desconocido: {tipo!r}")
    if sexo not in ("H", "M"):
        raise ValueError(f"sexo debe ser 'H' o 'M', no {sexo!r}")
    d = _datos()
    return d[f"{tipo}_{sexo}_q"], d[f"{tipo}_{sexo}_aa"]


def edad_en_meses(nacimiento: date, referencia: date) -> int:
    """Edad en meses a la fecha de simulación: el día de nacimiento >= 15 cuenta como mes siguiente y se suma 1 mes.

    El día del mes de la simulación no influye (solo importan mes y año).
    """
    return (
        12 * (referencia.year - nacimiento.year)
        + (referencia.month - nacimiento.month)
        - (1 if nacimiento.day >= 15 else 0)
        + A0_MESES
    )


def mes_absoluto(fecha: date) -> int:
    """Índice de mes (año*12 + mes-1) de la fecha de simulación."""
    return fecha.year * 12 + fecha.month - 1


def _q_mejorada(q0: np.ndarray, aa: np.ndarray, edad: int, n_anios: float) -> float:
    """q de la edad `edad` con n_anios (fraccionario) de mejoramiento acumulado, tomando los AA de esa misma edad."""
    if edad >= EDAD_MAX:
        return 1.0
    n_anios = max(n_anios, 0.0)
    n = int(np.floor(n_anios))
    fr = n_anios - n
    q = float(q0[edad])
    for j in range(1, n + 1):
        q *= 1.0 - aa[edad, min(j - 1, 15)]
    if fr > 0:
        q *= (1.0 - aa[edad, min(n, 15)]) ** fr
    return min(1.0, q)


def supervivencia(
    sexo: str, tipo: str, edad_meses0: int, t0_mes: int, n_meses: int = N_MAX_MESES
) -> np.ndarray:
    """s[m] = probabilidad de estar vivo al comienzo del mes m (s[0] = 1).

    Mejoramiento continuo: N = (t0_mes + m)/12 − 2020 + C_CALENDARIO años. Muertes uniformes dentro
    del año de edad (UDD) con la tasa q del año de edad cumplido; p_mes = (1 − (mu+1)/12·q) / (1 − mu/12·q),
    mu = mes dentro del año de edad.
    """
    q0, aa = tabla(sexo, tipo)
    s = np.zeros(n_meses)
    actual = 1.0
    cache: dict[tuple[int, float], float] = {}
    for m in range(n_meses):
        am = edad_meses0 + m
        x = am // 12
        if x > EDAD_MAX:
            break
        s[m] = actual
        n = (t0_mes + m) / 12.0 - 2020.0 + C_CALENDARIO
        clave = (x, round(n, 9))
        if clave not in cache:
            cache[clave] = _q_mejorada(q0, aa, x, n)
        q = cache[clave]
        mu = am % 12
        actual *= (1.0 - (mu + 1) / 12.0 * q) / (1.0 - mu / 12.0 * q)
    return s


def factores_tasa(tasa: float) -> tuple[float, float]:
    """(g, j): g = (1+i)^(1/12), j = g − 1, con i anual en fracción."""
    g = (1.0 + tasa) ** (1.0 / 12.0)
    return g, g - 1.0
