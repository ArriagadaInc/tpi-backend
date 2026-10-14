"""Renta vitalicia inmediata: causante (+ cónyuge) (+ hijos) con garantía y aumento temporal.

Ecuaciones (por 1 UF de pensión base del causante; detalle y evidencia en docs/SIM_RV_V1_MODELO.md):
    pago(m) = b(m) · ( 1            si m < G            (periodo garantizado: se paga completo)
                       u(m)         si m ≥ G )
    b(m)    = 1 + f·[m < T]         (el aumento multiplica todo el flujo, incluida la sobrevivencia)
    u(m)    = s_c(m) + (1 − s_c(m))·sob(m)
    A       = Σ_m g^−m · pago(m)
    Q       = 15·(g − j·A_causante)  A_causante = Σ_m g^−m·s_c(m)     (deducción por cuota mortuoria)
    P       = (S − Q) / A
"""

from __future__ import annotations

from datetime import date

import numpy as np

from .modelos import Hijo, Persona
from .mortalidad import edad_en_meses, factores_tasa, mes_absoluto, supervivencia

CUOTA_MORTUORIA_UF = 15.0
PCT_CONYUGE = 0.60  # pensión del cónyuge sobreviviente
PCT_CONYUGE_CON_HIJO_COMUN = 0.50  # mientras exista un hijo común con derecho a pensión
PCT_HIJO = 0.15
PCT_HIJO_PARCIAL_ADULTO = 0.11  # inválido parcial desde los 24 años
PCT_EXTRA_SIN_CONYUGE = 0.50  # sin cónyuge, se reparte 50% adicional entre los hijos con derecho
EDAD_LIMITE_HIJO_ANIOS = 24
ANIOS_TABLA_CAUSANTE = 111  # horizonte de la tabla del causante usado en la regla de garantía larga


def calcular(
    *,
    fecha: date,
    saldo: float,
    tasa_pct: float,
    causante: Persona,
    conyuge: Persona | None = None,
    hijos: tuple[Hijo, ...] = (),
    meses_garantizados: int = 0,
    meses_aumento: int = 0,
    aumento: float = 0.0,
) -> dict[str, float]:
    """aumento es la fracción (0.25 = 25%). Devuelve dict con P, A, Q, cnu."""
    g, j = factores_tasa(tasa_pct / 100.0)
    t0 = mes_absoluto(fecha)
    em_causante = edad_en_meses(causante.nacimiento, fecha)
    sc = supervivencia(causante.sexo, "vejez", em_causante, t0)
    n = len(sc)
    ss = None
    if conyuge is not None:
        ss = supervivencia(conyuge.sexo, "sobrev", edad_en_meses(conyuge.nacimiento, fecha), t0)
        n = min(n, len(ss))
    sc = sc[:n]
    m = np.arange(n)
    descuento = g ** (-m)
    horizonte_causante = ANIOS_TABLA_CAUSANTE * 12 - em_causante
    A_causante = float(np.sum(descuento * sc))

    # hijos: supervivencia, elegibilidad (por edad) y condición
    s_hijo: list[np.ndarray] = []
    elegible: list[np.ndarray] = []
    regular: list[np.ndarray] = []
    for h in hijos:
        em = edad_en_meses(h.nacimiento, fecha)
        tabla_hijo = "inval" if h.invalidez != "no" else "sobrev"
        s_hijo.append(supervivencia(h.sexo, tabla_hijo, em, t0, n_meses=n)[:n])
        por_edad = ((em + m) < EDAD_LIMITE_HIJO_ANIOS * 12).astype(float)
        regular.append(por_edad)
        elegible.append(np.ones(n) if h.invalidez != "no" else por_edad)

    if ss is not None:
        con_derecho_comun = [e for e, h in zip(elegible, hijos) if h.comun]
        hay_comun = np.maximum.reduce(con_derecho_comun) if con_derecho_comun else np.zeros(n)
        sobrevivencia = ss[:n] * (
            PCT_CONYUGE - (PCT_CONYUGE - PCT_CONYUGE_CON_HIJO_COMUN) * hay_comun
        )
    else:
        sobrevivencia = np.zeros(n)
    n_hijos = len(hijos)
    n_con_derecho = np.maximum(1.0, np.sum(elegible, axis=0)) if n_hijos else np.ones(n)
    for k, h in enumerate(hijos):
        pct: np.ndarray | float
        if h.invalidez == "parcial":
            pct = PCT_HIJO * regular[k] + PCT_HIJO_PARCIAL_ADULTO * (1.0 - regular[k])
        else:
            pct = PCT_HIJO
        cuota = pct if ss is not None else pct + PCT_EXTRA_SIN_CONYUGE / n_con_derecho
        flujo = s_hijo[k] * elegible[k]
        if meses_garantizados and meses_garantizados >= horizonte_causante:
            # garantía que cubre el resto de la tabla: el flujo propio del hijo se corta en G
            flujo = flujo * (m < meses_garantizados)
        sobrevivencia = sobrevivencia + cuota * flujo

    u = sc + (1.0 - sc) * sobrevivencia
    b = 1.0 + aumento * (m < meses_aumento)
    pago = b * np.where(m < meses_garantizados, 1.0, u)
    A = float(np.sum(descuento * pago))
    Q = CUOTA_MORTUORIA_UF * (g - j * A_causante)
    P = (saldo - Q) / A
    return dict(P=P, A=A, Q=Q, cnu=saldo * A / (saldo - Q))
