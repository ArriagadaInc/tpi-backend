"""Adaptador con el formato de la API del portal (solicitud y respuesta de `PensionMensual/Simular`).

Sirve para contrastar el motor con las respuestas reales del portal (fixture de 435 casos). Códigos
del portal: IdSexo 1 = hombre, 2 = mujer; IdTipoParentesco 1 = causante, 2 = cónyuge, 4 = hijo;
IdCondicionInvalidez 78 = no inválido, 80 = parcial, 84 = total; IdTipoPension 1 = vejez anticipada,
2 = vejez edad; IdTipoRVD 1 = RVD 50% de la RT, 2 = "Otro RVD" (con PorcentajeRelacionPensiones).
"""

from __future__ import annotations

from datetime import date
from typing import Any, cast

from .api import NoValidadoError, simular
from .modelos import Hijo, Invalidez, Persona, Resultado, Sexo

_SEXO: dict[int, Sexo] = {1: "H", 2: "M"}
_INVALIDEZ: dict[int, Invalidez] = {78: "no", 80: "parcial", 84: "total"}
_TIPO_PENSION: dict[int, str] = {1: "vejez_anticipada", 2: "vejez_edad"}


def _fecha(iso: str) -> date:
    """'2026-06-07T04:00:00.000Z' -> date(2026, 6, 7) (fecha civil de Chile)."""
    return date.fromisoformat(iso[:10])


def simular_solicitud(solicitud: dict[str, Any], tasa_venta_pct: float | None = None) -> Resultado:
    """Ejecuta el motor con una solicitud en el formato del portal.

    Si la solicitud no trae `TasaventaUsuario` (tasa automática del portal) hay que pasar
    `tasa_venta_pct` (la respuesta del portal la informa en `TasaVenta`).
    """
    tasa = solicitud.get("TasaventaUsuario", tasa_venta_pct)
    if tasa is None:
        raise ValueError(
            "falta la tasa de venta: la solicitud no trae TasaventaUsuario y no se pasó tasa_venta_pct"
        )
    causante: Persona | None = None
    conyuge: Persona | None = None
    hijos: list[Hijo] = []
    for g in solicitud["GrupoFamiliar"]:
        sexo = _SEXO[g["IdSexo"]]
        nac = _fecha(g["FechaNacimiento"])
        parentesco, inv = g["IdTipoParentesco"], _INVALIDEZ[g["IdCondicionInvalidez"]]
        if parentesco == 1:
            if inv != "no":
                raise NoValidadoError("causante inválido no reconstruido")
            causante = Persona(sexo, nac)
        elif parentesco == 2:
            if inv != "no":
                raise NoValidadoError("cónyuge inválido no reconstruido")
            conyuge = Persona(sexo, nac)
        elif parentesco == 4:
            hijos.append(
                Hijo(sexo, nac, comun=g.get("IdPadreMadreRelacionado", 0) == 2, invalidez=inv)
            )
        else:
            raise NoValidadoError(f"IdTipoParentesco {parentesco} no reconstruido")
    if causante is None:
        raise ValueError("la solicitud no trae causante (IdTipoParentesco 1)")
    anios = solicitud.get("AniosDiferidos", 0)
    id_rvd = solicitud.get("IdTipoRVD") or 0
    porcentaje_rvd = cast(
        float,
        {0: 100.0, 1: 50.0}.get(id_rvd, solicitud.get("PorcentajeRelacionPensiones") or 100.0),
    )
    return simular(
        fecha_simulacion=_fecha(solicitud["FechaSimulacion"]),
        saldo_uf=solicitud["SaldoCuentaAFP"],
        tasa_venta_pct=tasa,
        causante=causante,
        conyuge=conyuge,
        hijos=hijos,
        meses_garantizados=solicitud.get("MesesGarantizados", 0),
        meses_aumento_temporal=solicitud.get("MesesAumentoTemporal", 0),
        porcentaje_aumento_temporal=solicitud.get("PorcentajeAumentoTemporal", 0.0),
        anios_diferidos=anios,
        porcentaje_rvd=porcentaje_rvd if anios else 100.0,
        valor_nominal_bono=solicitud.get("MontoNominalBono", 0),
        tipo_pension=_TIPO_PENSION[solicitud["IdTipoPension"]],
    )


def a_respuesta_portal(r: Resultado, tasa_venta_pct: float) -> dict[str, Any]:
    """Campos de la respuesta del portal que el motor reproduce (no incluye TotalCuotaMortuoriaUnitaria ni ValorCesionBono)."""
    return {
        "MesesDiferidos": r.meses_diferidos,
        "PensionMensualEstimada": r.pension_mensual,
        "PrimaUnicaReferencial": round(r.prima_uf, 2),
        "PrimaNetaAfp": round(r.prima_neta_afp_uf, 2),
        "CnuPensionRentaVitalicia": round(r.cnu, 6),
        "TasaVenta": tasa_venta_pct,
    }
