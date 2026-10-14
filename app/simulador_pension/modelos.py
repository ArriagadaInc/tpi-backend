"""Tipos de entrada y salida de la API del simulador."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

Sexo = Literal["H", "M"]
Invalidez = Literal["no", "parcial", "total"]


@dataclass(frozen=True)
class Persona:
    sexo: Sexo
    nacimiento: date


@dataclass(frozen=True)
class Hijo:
    sexo: Sexo
    nacimiento: date
    comun: bool = False  # hijo común con el cónyuge (relación "2 - Cónyuge" en el portal)
    invalidez: Invalidez = "no"


@dataclass(frozen=True)
class Resultado:
    """Resultado de una simulación. Montos en UF."""

    pension_mensual: float  # PensionMensualEstimada del portal (2 decimales)
    pension_exacta: float  # sin redondear
    prima_uf: float  # PrimaUnicaReferencial (lo que se paga a la aseguradora)
    prima_neta_afp_uf: float  # PrimaNetaAfp (= saldo − prima; reserva RT + comisión)
    cnu: float  # CnuPensionRentaVitalicia = prima / pensión
    factor_a: float | None = None  # anualidad anticipada mensual efectiva (solo renta inmediata)
    deduccion_cuota_mortuoria_uf: float | None = None  # "Q" del causante, solo renta inmediata
    renta_temporal_mensual: float | None = (
        None  # RT mensual durante el diferimiento (solo diferida)
    )
    comision_uf: float | None = None  # término E de la AFP (solo diferida)
    meses_diferidos: int = 0
