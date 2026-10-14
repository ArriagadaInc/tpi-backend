"""Simulador de pensión mensual de renta vitalicia (reconstrucción empírica del portal).

    from datetime import date
    from app.simulador_pension import simular, Persona

    r = simular(fecha_simulacion=date(2026, 10, 5), saldo_uf=3000, tasa_venta_pct=4.7,
                causante=Persona("H", date(1961, 5, 15)))
    r.pension_mensual   # UF/mes

Módulo puro (sin I/O ni importaciones del resto de ``app``); alcance, tolerancia y límites
en ``docs/SIM_RV_V1_MODELO.md``.
"""

from .api import NoValidadoError, simular
from .modelos import Hijo, Persona, Resultado
from .portal import a_respuesta_portal, simular_solicitud

__all__ = [
    "simular",
    "simular_solicitud",
    "a_respuesta_portal",
    "Persona",
    "Hijo",
    "Resultado",
    "NoValidadoError",
]

__version__ = "1.0.0"
