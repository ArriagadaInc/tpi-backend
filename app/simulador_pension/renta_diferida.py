"""Renta temporal (AFP) + renta vitalicia diferida (aseguradora). Solo causante individual, sin garantía ni aumento.

    n = 12·N meses de diferimiento;   RT = P / r   (r = RVD/RT: 1, 0,5 o el % de "Otro RVD")
    Prima = A_def·P + Q_ins           A_def = Σ_{m ≥ n} s_m·g^−m     Q_ins = 15·Σ_{m ≥ n} (s_m − s_{m+1})·g^−m
    Reserva AFP = D·RT + E            D = 12·Σ_{k<N} 1,0367^−k        (anualidad anticipada anual al 3,67%, sin mortalidad)
    S = Prima + D·RT + E
    E = C·f                           C = min(KAPPA·a_N·RT, 60 UF)    a_N = Σ_{k<N} s_{12k}·1,0367^−k
                                      f = max(Prima/S, min(1, S0/S))  S0 = 3000 UF
Quedan casos anómalos documentados (capital entre ~3.000 y ~25.000 UF, N ≥ 6 y Prima/S bajo; error de hasta ~0,16 UF).
"""

from __future__ import annotations

from datetime import date

import numpy as np

from .modelos import Persona
from .mortalidad import edad_en_meses, factores_tasa, mes_absoluto, supervivencia

R_RT = 0.0367  # tasa de la renta temporal (retiro programado)
KAPPA = 0.2445  # coeficiente de la comisión sobre la renta temporal (medido, ±0,0001)
TOPE_COMISION_UF = 60.0
CAPITAL_PRORRATEO_UF = 3000.0
CUOTA_MORTUORIA_UF = 15.0


def calcular(
    *,
    fecha: date,
    saldo: float,
    tasa_pct: float,
    causante: Persona,
    anios_diferidos: int,
    relacion_rvd: float = 1.0,
) -> dict[str, float]:
    """relacion_rvd = RVD/RT en fracción (1.0, 0.5, 0.51 … 0.99)."""
    N = int(anios_diferidos)
    g, _ = factores_tasa(tasa_pct / 100.0)
    s = supervivencia(
        causante.sexo, "vejez", edad_en_meses(causante.nacimiento, fecha), mes_absoluto(fecha)
    )
    m = np.arange(len(s))
    v = g ** (-m)
    n = 12 * N
    s_sig = np.append(s[1:], 0.0)
    A_def = float(np.sum((s * v)[n:]))
    Q_ins = CUOTA_MORTUORIA_UF * float(np.sum(((s - s_sig) * v)[n:]))
    D = 12.0 * sum((1 + R_RT) ** (-k) for k in range(N))
    a_N = float(sum(s[12 * k] * (1 + R_RT) ** (-k) for k in range(N)))
    r = relacion_rvd

    def comision(P: float) -> float:
        prima = A_def * P + Q_ins
        f = max(prima / saldo, min(1.0, CAPITAL_PRORRATEO_UF / saldo))
        return min(KAPPA * a_N * P / r, TOPE_COMISION_UF) * f

    def exceso(P: float) -> float:  # creciente en P: S = Prima + D·RT + E
        return A_def * P + Q_ins + D * P / r + comision(P) - saldo

    lo, hi = 0.0, saldo
    for _ in range(200):
        medio = 0.5 * (lo + hi)
        if exceso(medio) > 0:
            hi = medio
        else:
            lo = medio
    P = 0.5 * (lo + hi)
    prima = A_def * P + Q_ins
    return dict(
        P=P,
        prima=prima,
        cnu=prima / P,
        renta_temporal=P / r,
        comision=comision(P),
        meses_diferidos=n,
    )
