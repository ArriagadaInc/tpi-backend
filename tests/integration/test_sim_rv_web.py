"""Integración (PostgreSQL real) del simulador de renta vitalicia (AC-10, AC-11).

Verifica que un PDF generado con éxito escribe un único evento append-only en
``tpi.auditoria`` sin PII, y que la simulación no persiste entradas/resultados ni altera
el estado, las notas ni las asignaciones del lead.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.models import AuthenticatedUser, AuthenticationResult, UserRole
from app.config import Settings
from app.database.connection import get_db_connection
from app.database.healthcheck import full_health_check
from app.services.simulador_service import codigo_verificacion
from app.simulador_pension import Persona, simular
from app.web.main import create_web_app

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session", autouse=True)
def verify_database() -> None:
    health = full_health_check()
    if not health.get("all_ready"):
        pytest.skip("Base de datos no disponible para tests de integración")


class _World:
    def __init__(self) -> None:
        self.suffix = uuid4().hex[:8]
        self.lead_id: Any = None
        self.persona_id: Any = None
        self.rut = f"7{int(uuid4().hex[:8], 16) % 90000000 + 10000000}-1"
        # Nombre con marcado y caracteres especiales (AC-2): el detalle no debe contenerlo.
        self.nombre = f'Simulador <b>Lead</b> & "Álvaro" ñ {self.suffix} <script>alert(1)</script>'


@pytest.fixture
def world() -> _World:
    w = _World()
    with get_db_connection(operation="sim_rv_world_setup") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM tpi.catalogo_genero WHERE nombre = 'Masculino' LIMIT 1")
            genero = cur.fetchone()
            genero_id = genero["id"] if genero else None
            cur.execute(
                "INSERT INTO tpi.personas (rut, nombre_completo, fecha_nacimiento, created_at) "
                "VALUES (%s, %s, %s, now()) RETURNING id_persona",
                (w.rut, w.nombre, date(1960, 1, 15)),
            )
            w.persona_id = cur.fetchone()["id_persona"]
            cur.execute(
                "INSERT INTO tpi.leads (id_persona, fecha_ingreso, genero_id, estado_lead, created_at) "
                "VALUES (%s, now(), %s, 'en_seguimiento', now()) RETURNING id_lead",
                (str(w.persona_id), str(genero_id) if genero_id else None),
            )
            w.lead_id = cur.fetchone()["id_lead"]
        conn.commit()

    yield w

    with get_db_connection(operation="sim_rv_world_cleanup") as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tpi.auditoria WHERE id_lead = %s", (str(w.lead_id),))
            cur.execute("DELETE FROM tpi.consentimientos WHERE id_lead = %s", (str(w.lead_id),))
            cur.execute("DELETE FROM tpi.asignaciones WHERE id_lead = %s", (str(w.lead_id),))
            cur.execute("DELETE FROM tpi.leads WHERE id_lead = %s", (str(w.lead_id),))
            cur.execute("DELETE FROM tpi.personas WHERE id_persona = %s", (str(w.persona_id),))
        conn.commit()


class _AuthProvider:
    def __init__(self, role: str) -> None:
        self._role = role

    def authenticate(self, username: str, password: str) -> AuthenticationResult:
        return AuthenticationResult(
            status="authenticated",
            user=AuthenticatedUser(
                subject=f"subject-{self._role}",
                username=username,
                display_name=f"User {self._role}",
                role=cast(UserRole, self._role),
            ),
        )


def _client(role: str) -> TestClient:
    app = create_web_app()
    app.state.auth_provider = _AuthProvider(role)
    app.state.settings = Settings(APP_ENV="local", AUTH_ENABLED=True, AUTH_MODE="simple-dev")
    client = TestClient(app)
    response = client.post(
        "/login", data={"username": f"{role}.local", "password": "x"}, follow_redirects=False
    )
    assert response.status_code == 303
    return client


def _csrf_token(client: TestClient, lead_id: str) -> str:
    body = client.get(f"/leads/{lead_id}/simulador").text
    match = re.search(r'name="csrf_token" value="([^"]+)"', body)
    assert match, body
    return match.group(1)


def _valid_form(csrf: str) -> dict[str, str]:
    return {
        "csrf_token": csrf,
        "saldo_uf": "3000",
        "tasa_venta_pct": "4.7",
        "meses_garantizados": "0",
        "meses_aumento_temporal": "0",
        "porcentaje_aumento_temporal": "0",
        "anios_diferidos": "0",
        "porcentaje_rvd": "100",
    }


def _auditoria(lead_id: Any) -> list[dict[str, Any]]:
    with get_db_connection(operation="sim_rv_read_auditoria") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT accion, tabla_afectada, id_lead, detalle FROM tpi.auditoria "
                "WHERE id_lead = %s AND accion = 'simulacion_renta_vitalicia'",
                (str(lead_id),),
            )
            return [dict(row) for row in cur.fetchall()]


def test_auditoria_sin_pii(world: _World) -> None:
    client = _client("executive")
    csrf = _csrf_token(client, str(world.lead_id))
    response = client.post(f"/leads/{str(world.lead_id)}/simulador", data=_valid_form(csrf))
    assert response.status_code == 200

    eventos = _auditoria(world.lead_id)
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento["accion"] == "simulacion_renta_vitalicia"
    assert evento["tabla_afectada"] == "tpi.leads"
    assert str(evento["id_lead"]) == str(world.lead_id)

    detalle = evento["detalle"]
    assert isinstance(detalle, dict)
    assert set(detalle.keys()) == {
        "schema_version",
        "actor_subject",
        "role",
        "tipo_escenario",
        "version_modelo",
        "codigo_verificacion",
        "entradas",
        "resultado",
    }
    assert detalle["schema_version"] == 1
    assert detalle["role"] == "executive"
    assert detalle["tipo_escenario"] == "renta_inmediata_causante"

    entradas = detalle["entradas"]
    assert entradas["saldo_uf"] == 3000.0
    assert entradas["tasa_venta_pct"] == 4.7
    assert entradas["valor_uf"] is None
    assert entradas["meses_garantizados"] == 0
    assert entradas["meses_aumento_temporal"] == 0
    assert entradas["anios_diferidos"] == 0
    assert entradas["causante"] == {"sexo": "H", "fecha_nacimiento": "1960-01-15"}
    assert entradas["beneficiarios"] == []
    assert detalle["resultado"]["pension_uf"] > 0
    assert detalle["resultado"]["renta_temporal_uf"] is None
    assert detalle["resultado"]["meses_diferidos"] == 0

    serialized = json.dumps(detalle, ensure_ascii=False)
    assert world.rut not in serialized
    # El nombre (con marcado y caracteres especiales) no aparece en el detalle.
    assert world.nombre not in serialized
    for fragmento in ("Simulador", "<b>", "Álvaro", "<script>", "alert"):
        assert fragmento not in serialized


def test_evidencia_reproducible(world: _World) -> None:
    """Las entradas guardadas reproducen la pensión y el código de verificación (AC-3)."""
    client = _client("executive")
    csrf = _csrf_token(client, str(world.lead_id))
    response = client.post(f"/leads/{str(world.lead_id)}/simulador", data=_valid_form(csrf))
    assert response.status_code == 200

    eventos = _auditoria(world.lead_id)
    assert len(eventos) == 1
    detalle = eventos[0]["detalle"]

    entradas = detalle["entradas"]
    kwargs = {
        "fecha_simulacion": date.fromisoformat(entradas["fecha_simulacion"]),
        "saldo_uf": entradas["saldo_uf"],
        "tasa_venta_pct": entradas["tasa_venta_pct"],
        "causante": Persona(
            entradas["causante"]["sexo"],
            date.fromisoformat(entradas["causante"]["fecha_nacimiento"]),
        ),
        "conyuge": None,
        "hijos": (),
        "meses_garantizados": entradas["meses_garantizados"],
        "meses_aumento_temporal": entradas["meses_aumento_temporal"],
        "porcentaje_aumento_temporal": entradas["pct_aumento_temporal"],
        "anios_diferidos": entradas["anios_diferidos"],
        "porcentaje_rvd": entradas["porcentaje_rvd"],
    }
    assert entradas["beneficiarios"] == []

    resultado = simular(**kwargs)
    codigo = codigo_verificacion(**kwargs)

    assert resultado.pension_mensual == detalle["resultado"]["pension_uf"]
    assert codigo == detalle["codigo_verificacion"]


def test_sin_persistencia(world: _World) -> None:
    def _estado() -> tuple[Any, Any, Any]:
        with get_db_connection(operation="sim_rv_read_lead") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT estado_lead, comentarios, saldo_afp FROM tpi.leads WHERE id_lead = %s",
                    (str(world.lead_id),),
                )
                row = cur.fetchone()
                return row["estado_lead"], row["comentarios"], row["saldo_afp"]

    antes = _estado()

    client = _client("executive")
    csrf = _csrf_token(client, str(world.lead_id))
    response = client.post(f"/leads/{str(world.lead_id)}/simulador", data=_valid_form(csrf))
    assert response.status_code == 200

    assert _estado() == antes

    with get_db_connection(operation="sim_rv_read_assignments") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM tpi.asignaciones WHERE id_lead = %s",
                (str(world.lead_id),),
            )
            assert cur.fetchone()["n"] == 0
