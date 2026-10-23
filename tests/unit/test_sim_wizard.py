"""Asistente de 3 pasos del simulador (SIM-WIZARD-3-PASOS): flujo, validación por paso y marca.

Cubre los AC-1..AC-5 del asistente: el indicador de 3 pasos, la validación del paso 1 en el
servidor (``continuar``), el cálculo en pantalla sin persistir ni auditar (``simular``), la
descarga del PDF con auditoría (``descargar_pdf``), el rechazo del cónyuge inválido, la
conservación de datos al volver y la marca TPI (JS propio, sin CDN nuevos, azul marino de la ficha).
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path
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

_APP_CSS = Path(__file__).resolve().parents[2] / "app" / "web" / "static" / "css" / "app.css"
_SIMULADOR_TEMPLATE = (
    Path(__file__).resolve().parents[2] / "app" / "web" / "templates" / "simulador.html"
)
_WIZARD_JS = (
    Path(__file__).resolve().parents[2] / "app" / "web" / "static" / "js" / "simulador_wizard.js"
)


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

    def get_solicitud_by_id(self, id_lead: Any) -> dict[str, Any] | None:
        return dict(self.row) if self.row is not None else None

    def get_crm_estado_lead_options(self) -> list[str]:
        return ["nuevo", "en_seguimiento", "cerrado", "asignado"]

    def get_lead_assignment_events(self, id_lead: Any) -> list[dict[str, Any]]:
        return []

    def get_lead_state_change_events(self, id_lead: Any) -> list[dict[str, Any]]:
        return []

    def get_lead_simulation_events(self, id_lead: Any) -> list[dict[str, Any]]:
        return []

    def get_asesores_disponibles_para_asignacion(self) -> list[dict[str, Any]]:
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


def _client(role: str = "executive", repo: _Repo | None = None) -> TestClient:
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


# --- AC-1: estructura del asistente -------------------------------------------


def test_wizard_muestra_tres_pasos_y_continuar() -> None:
    body = _client().get(f"/leads/{LEAD_ID_STR}/simulador").text
    assert "Datos de la simulación" in body
    assert "Grupo familiar" in body
    assert "Resultado" in body
    assert 'name="intent" value="continuar"' in body
    # El paso 1 es el activo por defecto.
    assert 'data-step="1"' in body
    assert 'data-step="2" hidden' in body


def test_wizard_muestra_aviso_referencial_y_logo_base() -> None:
    body = _client().get(f"/leads/{LEAD_ID_STR}/simulador").text
    assert "valores referenciales (no vinculantes)" in body
    # La marca se muestra a través del topbar compartido (logo oficial en base.html).
    assert "official-logo-on-light.png" in body


# --- AC-2: validación del paso 1 en el servidor --------------------------------


def test_continuar_valida_paso1_y_avanza_al_paso2() -> None:
    client = _client()
    csrf = _csrf_token(client)
    response = client.post(
        f"/leads/{LEAD_ID_STR}/simulador",
        data={**_valid_form(csrf), "intent": "continuar"},
    )
    assert response.status_code == 200
    assert 'name="intent" value="simular"' in response.text
    assert 'data-step="1" hidden' in response.text
    assert 'data-step="2" hidden' not in response.text


def test_continuar_paso1_invalido_422_y_conserva_valor() -> None:
    client = _client()
    csrf = _csrf_token(client)
    response = client.post(
        f"/leads/{LEAD_ID_STR}/simulador",
        data={**_valid_form(csrf), "intent": "continuar", "saldo_uf": "0"},
    )
    assert response.status_code == 422
    assert "El saldo en UF debe estar entre 500 y 100.000." in response.text
    assert 'name="saldo_uf" value="0"' in response.text
    # El error se muestra en el paso 1, que sigue activo.
    assert 'data-step="2" hidden' in response.text


# --- AC-4: calcular en pantalla no persiste ni audita --------------------------


def test_simular_muestra_resultado_sin_auditar() -> None:
    client = _client()
    csrf = _csrf_token(client)
    with patch("app.services.simulador_service.record_simulacion_event") as audit:
        response = client.post(
            f"/leads/{LEAD_ID_STR}/simulador",
            data={**_valid_form(csrf), "intent": "simular"},
        )
    assert response.status_code == 200
    assert "Monto pensión" in response.text
    assert "Saldo total" in response.text
    assert "Tasa de venta" in response.text
    assert "Valores referenciales, no vinculantes" in response.text
    assert 'name="intent" value="descargar_pdf"' in response.text
    audit.assert_not_called()


def test_simular_renta_temporal_muestra_tarjetas_extra() -> None:
    client = _client()
    csrf = _csrf_token(client)
    response = client.post(
        f"/leads/{LEAD_ID_STR}/simulador",
        data={**_valid_form(csrf), "intent": "simular", "anios_diferidos": "3"},
    )
    assert response.status_code == 200
    assert "Renta temporal" in response.text
    assert "Meses de diferimiento" in response.text


def test_descargar_pdf_con_intent_explicito_audita() -> None:
    client = _client()
    csrf = _csrf_token(client)
    with patch("app.services.simulador_service.record_simulacion_event") as audit:
        response = client.post(
            f"/leads/{LEAD_ID_STR}/simulador",
            data={**_valid_form(csrf), "intent": "descargar_pdf"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    audit.assert_called_once()


# --- AC-3: grupo familiar ------------------------------------------------------


def test_simular_rechaza_conyuge_invalido() -> None:
    client = _client()
    csrf = _csrf_token(client)
    response = client.post(
        f"/leads/{LEAD_ID_STR}/simulador",
        data={
            **_valid_form(csrf),
            "intent": "simular",
            "conyuge_sexo": "M",
            "conyuge_nacimiento": "1962-05-20",
            "conyuge_invalidez": "total",
        },
    )
    assert response.status_code == 422
    assert "cónyuge inválido" in response.text


def test_volver_paso1_conserva_datos_ingresados() -> None:
    client = _client()
    csrf = _csrf_token(client)
    response = client.post(
        f"/leads/{LEAD_ID_STR}/simulador",
        data={**_valid_form(csrf), "intent": "volver_paso1", "saldo_uf": "2500"},
    )
    assert response.status_code == 200
    assert 'name="saldo_uf" value="2500"' in response.text
    assert 'data-step="1" hidden' not in response.text


def test_wizard_preserva_beneficiarios_ocultos() -> None:
    """El formulario conserva los inputs ocultos de cónyuge e hijos entre pasos."""
    client = _client()
    csrf = _csrf_token(client)
    response = client.post(
        f"/leads/{LEAD_ID_STR}/simulador",
        data={
            **_valid_form(csrf),
            "intent": "volver_paso2",
            "conyuge_sexo": "M",
            "conyuge_nacimiento": "1962-05-20",
            "hijo_sexo_1": "H",
            "hijo_nacimiento_1": "2000-03-10",
            "hijo_comun_1": "1",
            "hijo_invalidez_1": "no",
        },
    )
    assert response.status_code == 200
    assert 'id="conyuge_sexo" value="M"' in response.text
    assert 'id="hijo_sexo_1" value="H"' in response.text


# --- AC-5: marca TPI, JS propio y sin CDN nuevos -------------------------------


def test_wizard_sin_cdn_ni_urls_externas_en_plantilla() -> None:
    contenido = _SIMULADOR_TEMPLATE.read_text(encoding="utf-8")
    for frag in ("https://", "http://", "unpkg", "cdn", "jsdelivr", "googleapis"):
        assert frag not in contenido, frag


def test_wizard_js_propio_existe_y_se_referencia_localmente() -> None:
    assert _WIZARD_JS.exists()
    contenido = _SIMULADOR_TEMPLATE.read_text(encoding="utf-8")
    assert "/static/js/simulador_wizard.js" in contenido


def test_wizard_usa_azul_marino_de_la_ficha() -> None:
    css = _APP_CSS.read_text(encoding="utf-8")
    assert "#0f243e" in css


def test_wizard_no_introduce_naranja_del_simulador_de_referencia() -> None:
    """El naranja de marca del simulador de referencia no aparece en el asistente ni en el PDF.

    Se vigilan los naranjas de marca más habituales; la paleta del CRM (teal) y el azul marino de
    la ficha son los únicos acentos del asistente.
    """
    css = _APP_CSS.read_text(encoding="utf-8")
    template = _SIMULADOR_TEMPLATE.read_text(encoding="utf-8")
    js = _WIZARD_JS.read_text(encoding="utf-8")
    for naranja in ("#ff6600", "#ff7a00", "#f97316", "#ff8c00", "#ea580c", "#ff5e00", "#fd6f00"):
        assert naranja not in css
        assert naranja not in template
        assert naranja not in js
