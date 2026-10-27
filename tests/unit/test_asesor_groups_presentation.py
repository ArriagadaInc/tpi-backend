"""Unit tests for the advisor grouping in the executive dashboard (AC-5).

``build_asesor_groups`` and ``build_asesor_cell_groups`` split the per-advisor summary
and the state x advisor matrix into Coordinadores and Runners (plus a defensive Socios
group) while keeping ``Sin asesor`` apart, with subtotals that only sum counts.
"""

from __future__ import annotations

from app.models.executive_dashboard import (
    GRUPO_COORDINADOR,
    GRUPO_RUNNER,
    GRUPO_SIN_ASESOR,
    GRUPO_SOCIO,
    AsesorRow,
    EstadoAsesorCell,
)
from app.web.dashboard_presentation import build_asesor_cell_groups, build_asesor_groups


def _asesor(
    id_asesor: str | None, grupo: str, *, total: int = 10, activa: int = 5, estancados: int = 1
) -> AsesorRow:
    return AsesorRow(
        id_asesor=id_asesor,
        nombre="Sin asesor" if id_asesor is None else f"Nombre {id_asesor}",
        cartera_total=total,
        cartera_activa=activa,
        estancados=estancados,
        grupo=grupo,
    )


def test_groups_split_coordinadores_and_runners_with_subtotals() -> None:
    rows = [
        _asesor("c1", GRUPO_COORDINADOR, total=10, activa=4, estancados=1),
        _asesor("c2", GRUPO_COORDINADOR, total=6, activa=3, estancados=2),
        _asesor("r1", GRUPO_RUNNER, total=8, activa=5, estancados=0),
    ]
    groups, sin_asesor = build_asesor_groups(rows)
    assert sin_asesor == []
    assert [g.titulo for g in groups] == ["Coordinadores", "Runners"]

    coord, runners = groups
    assert [r.id_asesor for r in coord.rows] == ["c1", "c2"]
    assert coord.subtotal_cartera_total == 16
    assert coord.subtotal_cartera_activa == 7
    assert coord.subtotal_estancados == 3

    assert [r.id_asesor for r in runners.rows] == ["r1"]
    assert runners.subtotal_cartera_total == 8


def test_sin_asesor_stays_apart_even_if_grupo_defaults_to_runner() -> None:
    rows = [
        _asesor("c1", GRUPO_COORDINADOR),
        _asesor(None, GRUPO_RUNNER),  # id None siempre se separa, sin importar grupo
    ]
    groups, sin_asesor = build_asesor_groups(rows)
    assert [r.id_asesor for r in sin_asesor] == [None]
    assert sin_asesor[0].nombre == "Sin asesor"
    assert all(g.titulo != "Sin asesor" for g in groups)


def test_socios_appear_only_as_defensive_group() -> None:
    rows = [_asesor("s1", GRUPO_SOCIO)]
    groups, sin_asesor = build_asesor_groups(rows)
    assert [g.titulo for g in groups] == ["Coordinadores", "Runners", "Socios"]
    assert groups[2].rows[0].id_asesor == "s1"


def test_empty_group_has_empty_label_and_zero_subtotal() -> None:
    groups, _ = build_asesor_groups([_asesor("r1", GRUPO_RUNNER)])
    coord = groups[0]
    assert coord.titulo == "Coordinadores"
    assert coord.empty_label == "Sin coordinadores con cartera"
    assert coord.rows == ()
    assert coord.subtotal_cartera_total == 0


def test_cell_groups_split_the_matrix() -> None:
    cells = [
        EstadoAsesorCell("c1", "Coord Uno", "nuevo", "Nuevo", 4, GRUPO_COORDINADOR),
        EstadoAsesorCell("r1", "Runner Uno", "nuevo", "Nuevo", 2, GRUPO_RUNNER),
        EstadoAsesorCell(None, "Sin asesor", "nuevo", "Nuevo", 1, GRUPO_SIN_ASESOR),
    ]
    groups, sin_asesor = build_asesor_cell_groups(cells)
    assert [g.titulo for g in groups] == ["Coordinadores", "Runners"]
    assert [c.id_asesor for c in groups[0].cells] == ["c1"]
    assert [c.id_asesor for c in groups[1].cells] == ["r1"]
    assert [c.id_asesor for c in sin_asesor] == [None]
