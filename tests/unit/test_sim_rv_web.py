"""Pruebas web (sin base de datos) del simulador de renta vitalicia (AC-1..AC-3, AC-9, AC-13).

Usa el ``SolicitudService`` real con un repositorio falso y la app FastAPI real para verificar:
el panel y la ruta solo para executive/ceo/cto, 403 real para el resto, anónimo → login, 404 con
lead no visible, precarga del formulario, validación del borde (422/CSRF) y los headers efímeros
del PDF sin RUT/correo/teléfono. La escritura de auditoría se sustituye por un mock.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any, cast
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient

from app.auth.models import AuthenticatedUser, AuthenticationResult, UserRole
from app.config import Settings
from app.services.solicitud_service import SolicitudService
from app.web.main import create_web_app

LEAD_ID = UUID("11111111-1111-1111-1111-111111111111")
LEAD_ID_STR = str(LEAD_ID)


def _row() -> dict[str, Any]:
    return {
        "id_lead": LEAD_ID_STR,
        "rut": "12.345.678-5",
        "nombre_completo": "Juan Perez",
        "email": "juan@example.com",
        "telefono": "+56 9 1234 5678",
        "fecha_nacimiento": date(1960, 1, 15),
        "genero": "Masculino",
        "estado_civil": "Casado",
        "afp": "Habitat",
        "saldo_afp": 1000000,
        "comentarios": "Solicitud original.",
        "estado_lead": "en_seguimiento",
        "created_at": datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
        "id_asesor": None,
        "asesor_nombre": None,
    }


class _Repo:
    def __init__(self) -> None:
        self.row: dict[str, Any] | None = _row()
        self.calls: list[str] = []

    def get_solicitud_by_id(self, id_lead: Any) -> dict[str, Any] | None:
        self.calls.append("get_solicitud_by_id")
        return dict(self.row) if self.row is not None else None

    def get_crm_estado_lead_options(self) -> list[str]:
        self.calls.append("get_crm_estado_lead_options")
        return ["nuevo", "en_seguimiento", "cerrado", "asignado"]

    def get_lead_assignment_events(self, id_lead: Any) -> list[dict[str, Any]]:
        self.calls.append("get_lead_assignment_events")
        return []

    def get_lead_state_change_events(self, id_lead: Any) -> list[dict[str, Any]]:
        self.calls.append("get_lead_state_change_events")
        return []

    def get_lead_simulation_events(self, id_lead: Any) -> list[dict[str, Any]]:
        self.calls.append("get_lead_simulation_events")
        return []

    def get_asesores_disponibles_para_asignacion(self) -> list[dict[str, Any]]:
        self.calls.append("get_asesores_disponibles_para_asignacion")
        return []


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


def _client(role: str, repo: _Repo | None = None) -> TestClient:
    service = SolicitudService(repository=cast(Any, repo or _Repo()))
    app = create_web_app()
    app.state.web_service = service
    app.state.auth_provider = _AuthProvider(role)
    app.state.settings = Settings(
        APP_ENV="local",
        AUTH_ENABLED=True,
        AUTH_MODE="simple-dev",
        AUTH_USERS_JSON='{"users":[]}',
        WEB_MASK_PII=True,
    )
    client = TestClient(app)
    response = client.post(
        "/login", data={"username": f"{role}.local", "password": "x"}, follow_redirects=False
    )
    assert response.status_code == 303
    return client


def _anonymous_client(repo: _Repo | None = None) -> TestClient:
    service = SolicitudService(repository=cast(Any, repo or _Repo()))
    app = create_web_app()
    app.state.web_service = service
    app.state.auth_provider = _AuthProvider("ceo")
    app.state.settings = Settings(APP_ENV="local", AUTH_ENABLED=True, AUTH_MODE="simple-dev")
    return TestClient(app)


def _csrf_token(client: TestClient) -> str:
    body = client.get(f"/leads/{LEAD_ID_STR}/simulador").text
    match = re.search(r'name="csrf_token" value="([^"]+)"', body)
    assert match, body
    return match.group(1)


def _valid_form(csrf: str) -> dict[str, str]:
    return {
        "csrf_token": csrf,
        "saldo_uf": "3000",
        "tasa_venta_pct": "4.7",
        "valor_uf": "",
        "meses_garantizados": "0",
        "meses_aumento_temporal": "0",
        "porcentaje_aumento_temporal": "0",
        "anios_diferidos": "0",
        "porcentaje_rvd": "100",
    }


# --- Autorización (AC-1) -------------------------------------------------------


def test_panel_visible_solo_para_executive_y_superusuarios() -> None:
    for role in ("executive", "ceo", "cto"):
        body = _client(role).get(f"/leads/{LEAD_ID_STR}").text
        assert "/simulador" in body, role
    for role in ("advisor", "admin", "operations", "readonly", "tester"):
        body = _client(role).get(f"/leads/{LEAD_ID_STR}").text
        assert "/simulador" not in body, role


def test_rol_no_autorizado_recibe_403() -> None:
    for role in ("advisor", "admin", "operations", "readonly", "tester"):
        client = _client(role)
        assert client.get(f"/leads/{LEAD_ID_STR}/simulador").status_code == 403, role
        csrf = "x"
        assert (
            client.post(f"/leads/{LEAD_ID_STR}/simulador", data=_valid_form(csrf)).status_code
            == 403
        ), role


def test_rol_no_autorizado_no_accede_al_repositorio() -> None:
    for role in ("advisor", "admin", "operations", "readonly", "tester"):
        repo = _Repo()
        client = _client(role, repo)
        repo.calls.clear()
        response = client.get(f"/leads/{LEAD_ID_STR}/simulador")
        assert response.status_code == 403, role
        assert repo.calls == [], role


def test_anonimo_redirige_a_login() -> None:
    repo = _Repo()
    client = _anonymous_client(repo)
    assert client.get(f"/leads/{LEAD_ID_STR}/simulador", follow_redirects=False).status_code == 307
    assert repo.calls == []


# --- Lead no visible (AC-2) ----------------------------------------------------


def test_lead_no_visible_404() -> None:
    repo = _Repo()
    repo.row = None
    client = _client("executive", repo)
    response = client.get(f"/leads/{LEAD_ID_STR}/simulador")
    assert response.status_code == 404


# --- Precarga del formulario (AC-3) -------------------------------------------


def test_formulario_precarga_sexo_y_fecha() -> None:
    body = _client("executive").get(f"/leads/{LEAD_ID_STR}/simulador").text
    assert 'value="H"' in body
    assert "15/01/1960" in body


def test_formulario_muestra_aviso_referencial_permanente() -> None:
    body = _client("executive").get(f"/leads/{LEAD_ID_STR}/simulador").text
    assert "valores referenciales (no vinculantes)" in body
    assert "ventana de validación" not in body


# --- Headers y entrega efímera (AC-9) -----------------------------------------


def test_headers_pdf_y_auditoria() -> None:
    client = _client("executive")
    csrf = _csrf_token(client)
    with patch("app.services.simulador_service.record_simulacion_event") as audit:
        response = client.post(f"/leads/{LEAD_ID_STR}/simulador", data=_valid_form(csrf))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="simulacion_rv_')
    assert disposition.endswith('.pdf"')
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content.startswith(b"%PDF")
    audit.assert_called_once()


def test_pdf_sin_rut_correo_telefono() -> None:
    client = _client("executive")
    csrf = _csrf_token(client)
    with patch("app.services.simulador_service.record_simulacion_event"):
        response = client.post(f"/leads/{LEAD_ID_STR}/simulador", data=_valid_form(csrf))
    assert response.status_code == 200
    body = response.content
    assert b"12.345.678-5" not in body
    assert b"juan@example.com" not in body
    assert b"+56 9 1234 5678" not in body


def test_auditoria_recibe_entradas_y_resultado() -> None:
    """El evento recibe las entradas (causante, cónyuge e hijos) y el resultado (AC-1)."""
    client = _client("executive")
    csrf = _csrf_token(client)
    form = {
        **_valid_form(csrf),
        "conyuge_sexo": "M",
        "conyuge_nacimiento": "1962-05-20",
        "hijo_sexo_1": "H",
        "hijo_nacimiento_1": "2000-03-10",
        "hijo_comun_1": "on",
        "hijo_invalidez_1": "no",
    }
    with patch("app.services.simulador_service.record_simulacion_event") as audit:
        response = client.post(f"/leads/{LEAD_ID_STR}/simulador", data=form)
    assert response.status_code == 200
    audit.assert_called_once()
    kwargs = audit.call_args.kwargs
    assert kwargs["tipo_escenario"] == "renta_inmediata_familia"
    assert kwargs["saldo_uf"] == 3000.0
    assert kwargs["tasa_venta_pct"] == 4.7
    assert kwargs["causante"].sexo == "H"
    assert kwargs["causante"].nacimiento == date(1960, 1, 15)
    assert kwargs["conyuge"].sexo == "M"
    assert kwargs["conyuge"].nacimiento == date(1962, 5, 20)
    assert len(kwargs["hijos"]) == 1
    assert kwargs["hijos"][0].comun is True
    assert kwargs["hijos"][0].invalidez == "no"
    assert kwargs["resultado"].pension_mensual > 0


# --- Validación del borde (AC-13) ---------------------------------------------


def test_validacion_servidor_422() -> None:
    client = _client("executive")
    csrf = _csrf_token(client)
    with patch("app.services.simulador_service.record_simulacion_event"):
        response = client.post(
            f"/leads/{LEAD_ID_STR}/simulador",
            data={**_valid_form(csrf), "saldo_uf": "0"},
        )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("text/html")
    assert "El saldo en UF debe estar entre 500 y 100.000." in response.text
    # El aviso se muestra en la misma pantalla del formulario, conservando lo ingresado.
    assert 'name="saldo_uf" value="0"' in response.text


def test_edad_fuera_de_rango_muestra_aviso_en_pantalla() -> None:
    repo = _Repo()
    repo.row["fecha_nacimiento"] = date(1990, 1, 1)  # ~36 años: fuera del rango validado
    client = _client("executive", repo)
    csrf = _csrf_token(client)
    with patch("app.services.simulador_service.record_simulacion_event"):
        response = client.post(f"/leads/{LEAD_ID_STR}/simulador", data=_valid_form(csrf))
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("text/html")
    assert "fuera del rango validado" in response.text
    assert 'name="saldo_uf" value="3000"' in response.text


def test_csrf_invalido_403() -> None:
    client = _client("executive")
    with patch("app.services.simulador_service.record_simulacion_event"):
        response = client.post(
            f"/leads/{LEAD_ID_STR}/simulador", data=_valid_form("token-invalido")
        )
    assert response.status_code == 403
