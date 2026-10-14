"""Ventana de validación fail-closed (AC-6)."""

from __future__ import annotations

from datetime import date, timedelta

from app.services.simulador_service import clasificar_ventana
from app.simulador_pension.api import VENTANA_VALIDADA


def test_dentro_de_ventana() -> None:
    inicio, fin = VENTANA_VALIDADA
    assert clasificar_ventana(inicio) == "ok"
    assert clasificar_ventana(fin) == "ok"
    assert clasificar_ventana(date(2026, 6, 15)) == "ok"


def test_advertencia_hasta_90_dias_despues() -> None:
    fin = VENTANA_VALIDADA[1]
    assert clasificar_ventana(fin + timedelta(days=1)) == "advertencia"
    assert clasificar_ventana(fin + timedelta(days=90)) == "advertencia"


def test_bloqueo_mas_alla_de_90_dias() -> None:
    fin = VENTANA_VALIDADA[1]
    assert clasificar_ventana(fin + timedelta(days=91)) == "bloqueado"
