"""Pruebas unitarias del dominio de la agenda (modelo y validaciones puras).

Cubre AC-1 (horario, duracion, pasado, modalidad, nota y los dos cambios de hora de
Chile) sin base de datos.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.agenda import (
    AGENDA_TZ,
    CITA_DURACIONES,
    AgendaConflictError,
    AgendaNotFoundError,
    AgendaPermissionError,
    AgendaValidationError,
    build_agenda_datetime,
    validate_duracion,
    validate_fin_dentro_de_horario,
    validate_inicio,
    validate_modalidad,
    validate_no_en_pasado,
    validate_nota,
)


def _dt(y: int, m: int, d: int, hh: int, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=AGENDA_TZ)


def test_duracion_valida():
    assert validate_duracion(30) == 30
    assert validate_duracion(45) == 45
    assert validate_duracion(60) == 60
    with pytest.raises(AgendaValidationError):
        validate_duracion(20)
    with pytest.raises(AgendaValidationError):
        validate_duracion(0)


def test_modalidad_valida():
    assert validate_modalidad("Google Meet") == "Google Meet"
    assert validate_modalidad("Llamada") == "Llamada"
    assert validate_modalidad("Presencial") == "Presencial"
    with pytest.raises(AgendaValidationError):
        validate_modalidad("WhatsApp")


def test_nota_valida_y_limite():
    assert validate_nota(None) is None
    assert validate_nota("   ") is None
    assert validate_nota("Revisar documentación") == "Revisar documentación"
    with pytest.raises(AgendaValidationError):
        validate_nota("x" * 501)
    assert validate_nota("x" * 500) == "x" * 500


def test_inicio_cada_15_minutos():
    assert validate_inicio(_dt(2026, 1, 15, 9, 0)) is not None
    assert validate_inicio(_dt(2026, 1, 15, 9, 15)) is not None
    with pytest.raises(AgendaValidationError):
        validate_inicio(_dt(2026, 1, 15, 9, 10))


def test_inicio_solo_lunes_a_viernes():
    # 2026-01-17 es sabado y 2026-01-18 domingo.
    with pytest.raises(AgendaValidationError):
        validate_inicio(_dt(2026, 1, 17, 9, 0))
    with pytest.raises(AgendaValidationError):
        validate_inicio(_dt(2026, 1, 18, 9, 0))
    # 2026-01-15 es jueves.
    assert validate_inicio(_dt(2026, 1, 15, 9, 0)) is not None


def test_inicio_desde_las_9():
    with pytest.raises(AgendaValidationError):
        validate_inicio(_dt(2026, 1, 15, 8, 45))
    assert validate_inicio(_dt(2026, 1, 15, 9, 0)) is not None


def test_inicio_exige_zona_horaria():
    with pytest.raises(AgendaValidationError):
        validate_inicio(datetime(2026, 1, 15, 9, 0))


def test_fin_dentro_del_horario():
    assert validate_fin_dentro_de_horario(_dt(2026, 1, 15, 18, 0), 60) is not None
    assert validate_fin_dentro_de_horario(_dt(2026, 1, 15, 18, 30), 30) is not None
    with pytest.raises(AgendaValidationError):
        validate_fin_dentro_de_horario(_dt(2026, 1, 15, 18, 30), 60)


def test_no_en_pasado():
    ahora = _dt(2026, 1, 15, 12, 0)
    assert validate_no_en_pasado(_dt(2026, 1, 15, 13, 0), ahora=ahora) is not None
    with pytest.raises(AgendaValidationError):
        validate_no_en_pasado(_dt(2026, 1, 15, 11, 0), ahora=ahora)
    with pytest.raises(AgendaValidationError):
        validate_no_en_pasado(_dt(2026, 1, 15, 12, 0), ahora=ahora)


def test_build_agenda_datetime():
    dt = build_agenda_datetime("2026-01-15", "09:30")
    assert dt == _dt(2026, 1, 15, 9, 30)
    with pytest.raises(AgendaValidationError):
        build_agenda_datetime("2026-13-40", "09:00")
    with pytest.raises(AgendaValidationError):
        build_agenda_datetime("2026-01-15", "9:70")
    with pytest.raises(AgendaValidationError):
        build_agenda_datetime("2026-01-15", "09:00:00:00")


def test_build_agenda_datetime_acepta_segundos():
    dt = build_agenda_datetime("2026-01-15", "09:30:00")
    assert dt == _dt(2026, 1, 15, 9, 30)


def test_cambios_de_hora_de_chile():
    """Los dos cambios de hora del ano: verano UTC-3 e invierno UTC-4."""
    verano = build_agenda_datetime("2026-01-15", "09:00")
    invierno = build_agenda_datetime("2026-07-15", "09:00")
    assert verano.utcoffset() == timedelta(hours=-3)
    assert invierno.utcoffset() == timedelta(hours=-4)
    # El mismo horario local corresponde a distinto instante UTC en cada epoca.
    assert verano.astimezone(UTC) != invierno.astimezone(UTC)


def test_horario_se_valida_en_hora_local_no_utc():
    """08:00 en invierno es 12:00 UTC; debe rechazarse por estar antes de las 09:00 local."""
    invierno = build_agenda_datetime("2026-07-15", "08:00")
    assert invierno.astimezone(UTC).hour == 12
    with pytest.raises(AgendaValidationError):
        validate_inicio(invierno)


def test_excepciones_llevan_status_code():
    assert AgendaValidationError("x").status_code == 400
    assert AgendaPermissionError("x").status_code == 403
    assert AgendaNotFoundError("x").status_code == 404
    assert AgendaConflictError("x").status_code == 409


def test_duraciones_constantes():
    assert set(CITA_DURACIONES) == {30, 45, 60}
