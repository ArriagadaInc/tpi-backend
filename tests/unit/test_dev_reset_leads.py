"""Pruebas de las partes puras y de las barreras de seguridad de ``scripts/dev_reset_leads.py``.

El script es una herramienta del humano contra DEV; aqui no se toca ninguna base ni AWS: se prueba
la generacion de datos ficticios, el orden de borrado, la deteccion de tablas desconocidas, el
borrado por lotes en S3 (con ``aws`` simulado) y que el script se niegue a correr fuera de DEV.
"""

from __future__ import annotations

import json
import random
import re
import tempfile
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.repositories.lead_activity_sql import NOTE_TS_PATTERN
from app.validators.rut import validate_rut
from scripts import dev_reset_leads as mod

AHORA = datetime(2026, 10, 24, 15, 0, tzinfo=UTC)


def _plan(semilla: int = 20261023) -> list[dict[str, Any]]:
    return mod.plan_de_leads(random.Random(semilla), AHORA)


@pytest.mark.parametrize(
    ("numero", "dv"),
    [(12345678, "5"), (11111111, "1"), (10000013, "K"), (22222222, "2")],
)
def test_dv_rut_calcula_el_digito_verificador(numero: int, dv: str) -> None:
    assert mod.dv_rut(numero) == dv
    assert validate_rut(f"{numero}-{dv}")


def test_el_plan_reparte_los_leads_en_los_12_estados() -> None:
    plan = _plan()

    assert Counter(lead["estado"] for lead in plan) == dict(mod.REPARTO)
    assert len(plan) == sum(cantidad for _, cantidad in mod.REPARTO) == 42
    assert len(mod.REPARTO) == 12


def test_el_plan_es_reproducible_por_semilla_y_distinto_con_otra() -> None:
    assert _plan(1) == _plan(1)
    assert _plan(1) != _plan(2)


def test_los_datos_ficticios_son_validos_y_unicos() -> None:
    plan = _plan()

    assert all(validate_rut(lead["rut"]) for lead in plan)
    assert len({lead["rut"] for lead in plan}) == len(plan)
    assert all(lead["email"].endswith("@example.test") for lead in plan)
    assert all(lead["telefono"].startswith("+569555") for lead in plan)


def test_los_estancados_son_los_esperados_y_el_resto_es_reciente() -> None:
    plan = _plan()
    asignados_activos = [
        lead for lead in plan if lead["estado"] != "nuevo" and lead["estado"] not in mod.INACTIVOS
    ]

    viejos = [lead for lead in asignados_activos if lead["ingreso"] <= AHORA - timedelta(days=8)]
    recientes = [lead for lead in asignados_activos if lead["ingreso"] > AHORA - timedelta(days=5)]

    assert len(viejos) == mod.ESTANCADOS
    assert len(viejos) + len(recientes) == len(asignados_activos)
    nuevos = [lead for lead in plan if lead["estado"] == "nuevo"]
    assert all(lead["ingreso"] > AHORA - timedelta(days=5) for lead in nuevos)


def test_las_notas_usan_el_encabezado_que_lee_la_app() -> None:
    plan = _plan()

    for lead in plan:
        if lead["estado"] in ("nuevo", "asignado"):
            assert lead["notas"] is None
            continue
        encabezados = re.findall(NOTE_TS_PATTERN, lead["notas"])
        assert 1 <= len(encabezados) <= 3
        assert lead["notas"].count("Equipo DEV\n") == len(encabezados)


class _CursorFalso:
    """Cursor minimo: registra las sentencias y devuelve filas preparadas."""

    def __init__(self, filas: list[dict[str, Any]] | None = None) -> None:
        self.sentencias: list[str] = []
        self._filas = filas or []

    def execute(self, consulta: str, params: Any = None) -> None:
        self.sentencias.append(consulta)

    def fetchall(self) -> list[dict[str, Any]]:
        return self._filas


def test_borrar_todo_vacia_las_dependientes_antes_de_leads_y_personas() -> None:
    cur = _CursorFalso()

    mod.borrar_todo(cur)

    tablas = [re.search(r"FROM (tpi\.\w+)", s).group(1) for s in cur.sentencias]  # type: ignore[union-attr]
    assert tablas[-2:] == ["tpi.leads", "tpi.personas"]
    assert set(tablas[:-2]) == {
        "tpi.api_idempotency",
        "tpi.consentimientos",
        "tpi.asignaciones",
        "tpi.fichas_diagnosticas",
        "tpi.citas",
        "tpi.eventos_lead",
        "tpi.campanas_atribucion",
        "tpi.ingesta_google_sheets",
        "tpi.auditoria",
    }
    ingesta = next(s for s in cur.sentencias if "ingesta_google_sheets" in s)
    assert "id_lead_generado IS NOT NULL" in ingesta


def test_una_tabla_dependiente_desconocida_detiene_el_script() -> None:
    fks = [
        {"tabla": "tpi.citas", "referencia": "tpi.leads", "columnas": "id_lead", "al_borrar": "a"},
        {
            "tabla": "tpi.detalle_cita",
            "referencia": "tpi.citas",
            "columnas": "id",
            "al_borrar": "a",
        },
    ]

    assert mod.dependientes_inesperados(_CursorFalso(fks)) == ["tpi.detalle_cita"]
    assert mod.dependientes_inesperados(_CursorFalso(fks[:1])) == []


def test_borrar_objetos_manda_lotes_de_mil_con_el_archivo_en_formato_cli(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    lotes: list[tuple[int, bool, str]] = []

    def aws_falso(args: list[str], profile: str, region: str) -> dict[str, Any]:
        valor = args[args.index("--delete") + 1]
        ruta = Path(valor.removeprefix("file://"))
        cuerpo = json.loads(ruta.read_text(encoding="utf-8"))
        lotes.append((len(cuerpo["Objects"]), cuerpo["Quiet"], valor[:7]))
        return {}

    monkeypatch.setattr(mod, "aws", aws_falso)

    borrados = mod.borrar_objetos([f"leads/{i}" for i in range(2500)], "perfil", "region")

    assert borrados == 2500
    assert lotes == [(1000, True, "file://"), (1000, True, "file://"), (500, True, "file://")]


def test_borrar_objetos_falla_si_s3_reporta_errores(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(mod, "aws", lambda *a, **k: {"Errors": [{"Key": "leads/1"}]})

    with pytest.raises(RuntimeError, match="no pudo borrar"):
        mod.borrar_objetos(["leads/1"], "perfil", "region")


class _ConfigFalsa:
    def __init__(self, host: str, user: str, database: str) -> None:
        self.host, self.user, self.database = host, user, database

    def safe_summary(self) -> str:
        return f"{self.host}/{self.database} user={self.user}"


class _AjustesFalsos:
    def __init__(self, config: _ConfigFalsa) -> None:
        self.database_config = config


@pytest.mark.parametrize(
    ("host", "user", "database", "motivo"),
    [
        ("db.interno.example", "tpi_admin", "tpi", "el host no es local"),
        ("localhost", "tpi_app", "tpi", "el usuario debe ser tpi_admin"),
        ("localhost", "tpi_admin", "tpi_local", "la base debe ser 'tpi'"),
    ],
)
def test_el_script_se_niega_a_correr_fuera_de_dev(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    host: str,
    user: str,
    database: str,
    motivo: str,
) -> None:
    monkeypatch.setattr(
        mod, "get_settings", lambda: _AjustesFalsos(_ConfigFalsa(host, user, database))
    )

    def no_debe_conectar(**_: Any) -> None:
        raise AssertionError("no debe abrir conexion cuando el destino no es DEV")

    monkeypatch.setattr(mod, "get_db_connection", no_debe_conectar)

    assert mod.main(["--sin-s3", "--ejecutar"]) == 2
    assert motivo in capsys.readouterr().err
