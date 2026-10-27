"""Pruebas de las funciones de presentación de la agenda (AC-2, CRM-AGENDA-3-LOOK).

Cubren los helpers puros (sin base de datos) que arman la nueva pantalla de la agenda:
colores por responsable, rango de fechas, etiqueta de día, carriles de reuniones
simultáneas, cuadrícula de la semana, resumen, agrupación por día y ficha de fecha.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.models.agenda import AGENDA_TZ
from app.web.agenda_presentation import (
    _asignar_carriles,
    agrupar_por_dia,
    build_week_grid,
    color_map,
    etiqueta_dia,
    meeting_tile,
    rango_label,
    resumen_semana,
)

# ------------------------------------------------------------------ color_map


def test_color_map_orden_alfabetico() -> None:
    responsables = [
        {"nombre": "Zeta"},
        {"nombre": "Alfa"},
        {"nombre": "Medio"},
    ]
    assert color_map(responsables) == {
        "Alfa": "accent",
        "Medio": "info",
        "Zeta": "violet",
    }


def test_color_map_cicla_la_paleta() -> None:
    responsables = [{"nombre": f"n{i}"} for i in range(6)]
    assert color_map(responsables) == {
        "n0": "accent",
        "n1": "info",
        "n2": "violet",
        "n3": "warning",
        "n4": "accent",
        "n5": "info",
    }


def test_color_map_nombre_desconocido_usa_color_neutro() -> None:
    # El color neutro ("slate") es el fallback que usan las vistas cuando el nombre
    # no está en el mapa; color_map no inventa colores para nombres desconocidos.
    mapa = color_map([{"nombre": "Alfa"}])
    assert mapa.get("Desconocido", "slate") == "slate"
    assert "Desconocido" not in mapa


# ------------------------------------------------------------------ rango_label


def test_rango_label_semana_dentro_de_un_mes() -> None:
    assert rango_label(date(2026, 10, 26)) == "26 – 30 oct 2026"


def test_rango_label_semana_que_cruza_dos_meses() -> None:
    assert rango_label(date(2026, 9, 28)) == "28 sep – 2 oct 2026"


# ------------------------------------------------------------------ etiqueta_dia


def test_etiqueta_dia_hoy() -> None:
    assert etiqueta_dia(date(2026, 10, 26), date(2026, 10, 26)) == "Hoy"


def test_etiqueta_dia_manana() -> None:
    assert etiqueta_dia(date(2026, 10, 27), date(2026, 10, 26)) == "Mañana"


def test_etiqueta_dia_con_fecha() -> None:
    assert etiqueta_dia(date(2026, 10, 28), date(2026, 10, 26)) == "Mié 28 oct"


# ------------------------------------------------------------------ _asignar_carriles


def test_asignar_carriles_reuniones_que_no_se_pisan() -> None:
    eventos = [
        {"start": 60, "dur": 30},
        {"start": 0, "dur": 30},
    ]
    _asignar_carriles(eventos)
    por_start = {e["start"]: e for e in eventos}
    assert por_start[0]["lane"] == 0
    assert por_start[0]["lanes"] == 1
    assert por_start[60]["lane"] == 0
    assert por_start[60]["lanes"] == 1


def test_asignar_carriles_dos_simultaneas() -> None:
    eventos = [
        {"start": 0, "dur": 60},
        {"start": 30, "dur": 60},
    ]
    _asignar_carriles(eventos)
    por_start = {e["start"]: e for e in eventos}
    assert por_start[0]["lane"] == 0
    assert por_start[0]["lanes"] == 2
    assert por_start[30]["lane"] == 1
    assert por_start[30]["lanes"] == 2


def test_asignar_carriles_tres_encadenadas() -> None:
    eventos = [
        {"start": 0, "dur": 30},
        {"start": 30, "dur": 30},
        {"start": 60, "dur": 30},
    ]
    _asignar_carriles(eventos)
    for e in eventos:
        assert e["lane"] == 0
        assert e["lanes"] == 1


def test_asignar_carriles_grupo_termina_antes_del_siguiente() -> None:
    eventos = [
        {"start": 0, "dur": 30},
        {"start": 15, "dur": 30},
        {"start": 120, "dur": 30},
    ]
    _asignar_carriles(eventos)
    por_start = {e["start"]: e for e in eventos}
    assert por_start[0]["lane"] == 0
    assert por_start[0]["lanes"] == 2
    assert por_start[15]["lane"] == 1
    assert por_start[15]["lanes"] == 2
    assert por_start[120]["lane"] == 0
    assert por_start[120]["lanes"] == 1


# ------------------------------------------------------------------ build_week_grid


def _cita(dia: date, hora: int, duracion: int, nombre: str = "Socio A") -> dict:
    inicio = datetime(dia.year, dia.month, dia.day, hora, 0, tzinfo=AGENDA_TZ)
    return {
        "fecha_hora": inicio,
        "fecha_hora_fin": inicio + timedelta(minutes=duracion),
        "asesor_nombre": nombre,
    }


def test_build_week_grid_lunes_a_viernes() -> None:
    lunes = date(2026, 10, 26)
    grid = build_week_grid([], lunes, lunes, datetime(2026, 10, 26, 9, 0, tzinfo=AGENDA_TZ), {})
    assert [d["fecha"] for d in grid] == [lunes + timedelta(days=i) for i in range(5)]
    assert [d["dow"] for d in grid] == ["lun", "mar", "mié", "jue", "vie"]


def test_build_week_grid_posicion_y_duracion_en_minutos() -> None:
    lunes = date(2026, 10, 26)
    grid = build_week_grid(
        [_cita(lunes, 10, 45)],
        lunes,
        lunes,
        datetime(2026, 10, 26, 9, 0, tzinfo=AGENDA_TZ),
        {},
    )
    eventos = grid[0]["eventos"]
    assert len(eventos) == 1
    assert eventos[0]["start"] == 60  # 10:00 - 09:00
    assert eventos[0]["dur"] == 45


def test_build_week_grid_dia_actual_y_linea_de_ahora() -> None:
    lunes = date(2026, 10, 26)
    grid = build_week_grid(
        [],
        lunes,
        lunes,
        datetime(2026, 10, 26, 10, 30, tzinfo=AGENDA_TZ),
        {},
    )
    assert grid[0]["es_hoy"] is True
    assert grid[0]["ahora"] == 90  # 10:30 - 09:00
    for d in grid[1:]:
        assert d["es_hoy"] is False
        assert d["ahora"] is None


def test_build_week_grid_linea_de_ahora_solo_dentro_del_horario() -> None:
    lunes = date(2026, 10, 26)
    antes = build_week_grid([], lunes, lunes, datetime(2026, 10, 26, 8, 0, tzinfo=AGENDA_TZ), {})
    assert antes[0]["ahora"] is None
    despues = build_week_grid([], lunes, lunes, datetime(2026, 10, 26, 20, 0, tzinfo=AGENDA_TZ), {})
    assert despues[0]["ahora"] is None


def test_build_week_grid_excluye_reuniones_de_otros_dias() -> None:
    lunes = date(2026, 10, 26)
    martes = lunes + timedelta(days=1)
    sabado = lunes + timedelta(days=5)
    grid = build_week_grid(
        [_cita(sabado, 10, 30), _cita(martes, 10, 30)],
        lunes,
        lunes,
        datetime(2026, 10, 26, 9, 0, tzinfo=AGENDA_TZ),
        {},
    )
    assert len(grid) == 5
    assert len(grid[0]["eventos"]) == 0  # lunes sin reuniones
    assert len(grid[1]["eventos"]) == 1  # martes con su reunión
    assert sum(len(d["eventos"]) for d in grid) == 1  # el sábado queda fuera


def test_build_week_grid_color_por_responsable() -> None:
    lunes = date(2026, 10, 26)
    grid = build_week_grid(
        [_cita(lunes, 10, 30, "Socio A")],
        lunes,
        lunes,
        datetime(2026, 10, 26, 9, 0, tzinfo=AGENDA_TZ),
        {"Socio A": "accent"},
    )
    assert grid[0]["eventos"][0]["color"] == "accent"
    # Sin color asignado se usa el neutro.
    grid2 = build_week_grid(
        [_cita(lunes, 10, 30, "Otro")],
        lunes,
        lunes,
        datetime(2026, 10, 26, 9, 0, tzinfo=AGENDA_TZ),
        {},
    )
    assert grid2[0]["eventos"][0]["color"] == "slate"


# ------------------------------------------------------------------ resumen_semana


def test_resumen_semana() -> None:
    citas = [
        {"estado_cita": "agendada"},
        {"estado_cita": "agendada"},
        {"estado_cita": "realizada"},
        {"estado_cita": "no_asistio"},
        {"estado_cita": "cancelada"},
        {"estado_cita": "estado_desconocido"},
    ]
    assert resumen_semana(citas) == {
        "agendada": 2,
        "realizada": 1,
        "no_asistio": 1,
        "cancelada": 1,
    }


# ------------------------------------------------------------------ agrupar_por_dia


def test_agrupar_por_dia() -> None:
    hoy = date(2026, 10, 26)
    lunes = datetime(2026, 10, 26, 10, 0, tzinfo=AGENDA_TZ)
    martes = datetime(2026, 10, 27, 11, 0, tzinfo=AGENDA_TZ)
    citas = [
        {
            "fecha_hora": martes,
            "fecha_hora_fin": martes + timedelta(minutes=30),
            "asesor_nombre": "Socio A",
        },
        {
            "fecha_hora": lunes,
            "fecha_hora_fin": lunes + timedelta(minutes=30),
            "asesor_nombre": "Socio B",
        },
    ]
    grupos = agrupar_por_dia(citas, hoy, {})
    assert [g["fecha"] for g in grupos] == [date(2026, 10, 26), date(2026, 10, 27)]
    assert grupos[0]["label"] == "Hoy"
    assert grupos[1]["label"] == "Mañana"
    assert grupos[0]["es_hoy"] is True
    assert grupos[1]["es_hoy"] is False
    assert [r["dur"] for r in grupos[0]["reuniones"]] == [30]


# ------------------------------------------------------------------ meeting_tile


def test_meeting_tile_hoy() -> None:
    tile = meeting_tile(datetime(2026, 10, 26, 10, 0, tzinfo=AGENDA_TZ), date(2026, 10, 26))
    assert tile == {"mes": "OCT", "dia": 26, "dow": "LUN", "relativo": "Hoy"}


def test_meeting_tile_manana() -> None:
    tile = meeting_tile(datetime(2026, 10, 27, 10, 0, tzinfo=AGENDA_TZ), date(2026, 10, 26))
    assert tile["relativo"] == "Mañana"


def test_meeting_tile_en_n_dias() -> None:
    tile = meeting_tile(datetime(2026, 10, 29, 10, 0, tzinfo=AGENDA_TZ), date(2026, 10, 26))
    assert tile["relativo"] == "En 3 días"


def test_meeting_tile_ya_paso() -> None:
    tile = meeting_tile(datetime(2026, 10, 25, 10, 0, tzinfo=AGENDA_TZ), date(2026, 10, 26))
    assert tile["relativo"] == "Ya pasó"
