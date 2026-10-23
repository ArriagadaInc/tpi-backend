"""Unit tests for the simulation timeline merge (presentation layer, SIM-HISTORIAL-LINEA-TIEMPO)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.web.presentation import FollowUpNote, build_timeline_items

_TZ = ZoneInfo("America/Santiago")


def _simulation(
    fecha_hora: datetime | None,
    *,
    actor: str = "user-003",
    tipo_escenario: str = "renta_inmediata_familia",
    codigo: str = "abc123def456",
    pension_uf: float = 5.23,
) -> dict:
    return {
        "id_auditoria": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "id_lead": "22222222-2222-2222-2222-222222222222",
        "fecha_hora": fecha_hora,
        "actor_subject": actor,
        "tipo_escenario": tipo_escenario,
        "version_modelo": "sim-rv-v1",
        "codigo_verificacion": codigo,
        "entradas": {
            "fecha_simulacion": "2026-10-15",
            "saldo_uf": 1000.0,
            "causante": {"sexo": "H", "fecha_nacimiento": "1960-01-15"},
            "beneficiarios": [
                {
                    "parentesco": "conyuge",
                    "sexo": "M",
                    "fecha_nacimiento": "1962-03-20",
                    "invalidez": None,
                    "comun": None,
                }
            ],
        },
        "resultado": {"pension_uf": pension_uf, "renta_temporal_uf": None, "meses_diferidos": 0},
    }


def _note(timestamp: str, author: str = "Alvaro", text: str = "Nota") -> FollowUpNote:
    return FollowUpNote(timestamp=timestamp, author=author, text=text)


def test_simulation_item_is_merged_and_exposes_summary_fields() -> None:
    items = build_timeline_items(
        [],
        [],
        [],
        [_simulation(datetime(2026, 9, 5, 12, 0, tzinfo=_TZ))],
    )

    assert len(items) == 1
    item = items[0]
    assert item["kind"] == "simulation"
    assert item["actor"] == "user-003"
    assert item["tipo_escenario"] == "renta_inmediata_familia"
    assert item["codigo_verificacion"] == "abc123def456"
    assert item["pension_uf"] == 5.23


def test_simulation_item_exposes_complete_entradas_and_resultado() -> None:
    items = build_timeline_items([], [], [], [_simulation(datetime(2026, 9, 5, 12, 0, tzinfo=_TZ))])

    item = items[0]
    assert item["entradas"]["saldo_uf"] == 1000.0
    assert item["entradas"]["causante"]["sexo"] == "H"
    assert item["entradas"]["beneficiarios"][0]["parentesco"] == "conyuge"
    assert item["resultado"]["pension_uf"] == 5.23
    assert item["renta_temporal_uf"] is None
    assert item["meses_diferidos"] == 0


def test_simulation_timestamp_is_displayed_in_america_santiago() -> None:
    utc_time = datetime(2026, 8, 5, 14, 30, tzinfo=UTC)
    items = build_timeline_items([], [], [], [_simulation(utc_time)])

    expected = utc_time.astimezone(_TZ).strftime("%d/%m/%Y %H:%M")
    assert items[0]["display_time"] == expected
    assert items[0]["timestamp"].tzinfo is not None


def test_simulation_without_timestamp_is_skipped() -> None:
    items = build_timeline_items([], [_note("05/09/2026 10:00")], [], [_simulation(None)])

    assert [item["kind"] for item in items] == ["note"]


def test_simulation_ranks_between_event_and_state_change_on_tie() -> None:
    moment = datetime(2026, 9, 5, 10, 0, tzinfo=_TZ)
    event = {
        "fecha_hora": moment,
        "actor_subject": "user-001",
        "asesor_nombre": "Asesor Demo",
        "estado_anterior": "nuevo",
        "estado_nuevo": "asignado",
    }
    state_change = {
        "fecha_hora": moment,
        "actor_subject": "user-002",
        "estado_anterior": "en_seguimiento",
        "estado_nuevo": "cerrado",
    }
    items = build_timeline_items([event], [], [state_change], [_simulation(moment)])

    assert [item["kind"] for item in items] == ["event", "simulation", "state_change"]


def test_simulation_with_missing_resultado_does_not_raise() -> None:
    sim = _simulation(datetime(2026, 9, 5, 12, 0, tzinfo=_TZ))
    sim["resultado"] = None
    sim["entradas"] = None

    items = build_timeline_items([], [], [], [sim])

    assert items[0]["pension_uf"] is None
    assert items[0]["entradas"]["causante"]["sexo"] is None
    assert items[0]["resultado"]["pension_uf"] is None


def test_legacy_simulation_is_flagged_and_normalized() -> None:
    sim = {
        "fecha_hora": datetime(2026, 9, 5, 12, 0, tzinfo=_TZ),
        "actor_subject": "user-001",
        "tipo_escenario": "renta_inmediata_familia",
        "version_modelo": "sim-rv-v1",
        "codigo_verificacion": "abc123",
        "entradas": None,
        "resultado": None,
    }

    items = build_timeline_items([], [], [], [sim])

    item = items[0]
    assert item["kind"] == "simulation"
    assert item["es_legacy"] is True
    assert item["actor"] == "user-001"
    assert item["tipo_escenario"] == "renta_inmediata_familia"
    assert item["version_modelo"] == "sim-rv-v1"
    assert item["codigo_verificacion"] == "abc123"
    assert item["entradas"]["causante"]["sexo"] is None
    assert item["entradas"]["causante"]["fecha_nacimiento"] is None
    assert item["entradas"]["beneficiarios"] == []
    assert item["resultado"]["pension_uf"] is None
    assert item["resultado"]["renta_temporal_uf"] is None
    assert item["resultado"]["meses_diferidos"] is None


def test_partial_entradas_without_causante_or_beneficiarios_does_not_raise() -> None:
    sim = {
        "fecha_hora": datetime(2026, 9, 5, 12, 0, tzinfo=_TZ),
        "actor_subject": "user-001",
        "tipo_escenario": "renta_inmediata_familia",
        "version_modelo": "sim-rv-v1",
        "codigo_verificacion": "abc123",
        "entradas": {"saldo_uf": 1000.0},
        "resultado": None,
    }

    items = build_timeline_items([], [], [], [sim])

    item = items[0]
    # Entradas present but resultado missing: not a legacy event.
    assert item["es_legacy"] is False
    assert item["entradas"]["saldo_uf"] == 1000.0
    assert item["entradas"]["causante"]["sexo"] is None
    assert item["entradas"]["causante"]["fecha_nacimiento"] is None
    assert item["entradas"]["beneficiarios"] == []
    assert item["pension_uf"] is None
    assert item["resultado"]["pension_uf"] is None


def test_beneficiario_with_missing_fields_and_null_dates_does_not_raise() -> None:
    sim = {
        "fecha_hora": datetime(2026, 9, 5, 12, 0, tzinfo=_TZ),
        "actor_subject": "user-001",
        "tipo_escenario": "renta_inmediata_familia",
        "version_modelo": "sim-rv-v1",
        "codigo_verificacion": "abc123",
        "entradas": {
            "fecha_simulacion": None,
            "causante": {"sexo": "H"},
            "beneficiarios": [{"parentesco": "hijo"}],
        },
        "resultado": {"pension_uf": 5.23},
    }

    items = build_timeline_items([], [], [], [sim])

    item = items[0]
    assert item["es_legacy"] is False
    assert item["entradas"]["fecha_simulacion"] is None
    assert item["entradas"]["causante"]["sexo"] == "H"
    assert item["entradas"]["causante"]["fecha_nacimiento"] is None
    beneficiario = item["entradas"]["beneficiarios"][0]
    assert beneficiario["parentesco"] == "hijo"
    assert beneficiario["sexo"] is None
    assert beneficiario["fecha_nacimiento"] is None
    assert beneficiario["invalidez"] is None
    assert beneficiario["comun"] is None
    assert item["pension_uf"] == 5.23
