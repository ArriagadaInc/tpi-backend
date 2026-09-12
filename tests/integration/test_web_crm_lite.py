"""Integration tests for the FastAPI web CRM against real local PostgreSQL."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.auth.models import AuthenticatedUser, AuthenticationResult
from app.database.connection import get_db_connection
from app.database.healthcheck import full_health_check
from app.models.solicitud import (
    ConsentimientosData,
    PersonaData,
    RegistrarSolicitudRequest,
    SolicitudData,
)
from app.services.solicitud_service import SolicitudService
from app.web.main import create_web_app

pytestmark = pytest.mark.integration


class _FakeAuthProvider:
    def __init__(self, role: str = "tester") -> None:
        self.role = role

    def authenticate(self, username: str, password: str) -> AuthenticationResult:
        if username == "diego" and password == "Secret123!":
            return AuthenticationResult(
                status="authenticated",
                user=AuthenticatedUser(
                    subject="user-001",
                    username="diego",
                    display_name="Diego",
                    role=self.role,
                ),
            )
        return AuthenticationResult(status="invalid")


@pytest.fixture(scope="session", autouse=True)
def verify_database():
    health = full_health_check()
    if not health.get("all_ready"):
        pytest.skip("Base de datos no disponible para tests de integración")


@pytest.fixture
def web_client() -> TestClient:
    app = create_web_app()
    app.state.web_service = SolicitudService()
    app.state.auth_provider = _FakeAuthProvider(role="tester")
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "diego", "password": "Secret123!"},
        follow_redirects=False,
    )
    return client


@pytest.fixture
def readonly_client() -> TestClient:
    app = create_web_app()
    app.state.web_service = SolicitudService()
    app.state.auth_provider = _FakeAuthProvider(role="readonly")
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "diego", "password": "Secret123!"},
        follow_redirects=False,
    )
    return client


@pytest.fixture
def service() -> SolicitudService:
    return SolicitudService()


def _cleanup(id_lead: UUID) -> None:
    with get_db_connection(operation="test_web_crm_lite_cleanup") as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tpi.auditoria WHERE id_lead = %s", (str(id_lead),))
            cur.execute("DELETE FROM tpi.asignaciones WHERE id_lead = %s", (str(id_lead),))
            cur.execute("DELETE FROM tpi.consentimientos WHERE id_lead = %s", (str(id_lead),))
            cur.execute("DELETE FROM tpi.leads WHERE id_lead = %s", (str(id_lead),))
        conn.commit()


def _extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def test_web_board_shows_real_lead_and_paginates(
    web_client: TestClient, service: SolicitudService
) -> None:
    afp_id = UUID(str(service.get_catalogo_afp()[0]["id"]))
    genero_id = UUID(str(service.get_catalogo_genero()[0]["id"]))
    estado_civil_id = UUID(str(service.get_catalogo_estado_civil()[0]["id"]))
    request = RegistrarSolicitudRequest(
        persona=PersonaData(
            rut="25000000-5",
            nombre_completo="Web CRM Integration",
            email="web.crm.integration@example.com",
            telefono="+56955556666",
            fecha_nacimiento=date(1990, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=genero_id,
            estado_civil_id=estado_civil_id,
            afp_id=afp_id,
            saldo_afp=Decimal("2300000"),
            comentarios="Lead de prueba para la web real",
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )
    response = service.registrar_solicitud(request)
    try:
        board = web_client.get("/leads", params={"search": "Web CRM Integration"})
        assert board.status_code == 200
        assert "Web CRM Integration" in board.text
        assert "Buscar por nombre o RUT" in board.text
        assert "AFP" in board.text
        assert "Estado" in board.text
        assert "Detalle del lead" not in board.text

        detail = web_client.get(f"/leads/{response.id_lead}")
        assert detail.status_code == 200
        assert "Buscar por nombre o RUT" not in detail.text
        assert "Mostrando" not in detail.text
        assert "Web CRM Integration" in detail.text
        assert "Abrir simulación" in detail.text
        assert "Fecha de nacimiento" in detail.text or "Fecha solicitud" in detail.text
    finally:
        _cleanup(response.id_lead)


def test_web_status_update_and_comment_append_persist(
    web_client: TestClient, service: SolicitudService
) -> None:
    afp_id = UUID(str(service.get_catalogo_afp()[0]["id"]))
    genero_id = UUID(str(service.get_catalogo_genero()[0]["id"]))
    estado_civil_id = UUID(str(service.get_catalogo_estado_civil()[0]["id"]))
    request = RegistrarSolicitudRequest(
        persona=PersonaData(
            rut="25000001-3",
            nombre_completo="Web CRM Follow Up",
            email="web.crm.follow.up@example.com",
            telefono="+56955557777",
            fecha_nacimiento=date(1990, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=genero_id,
            estado_civil_id=estado_civil_id,
            afp_id=afp_id,
            saldo_afp=Decimal("2300000"),
            comentarios="Comentario historico inicial",
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )
    response = service.registrar_solicitud(request)
    try:
        detail = web_client.get(f"/leads/{response.id_lead}")
        csrf = _extract_csrf(detail.text)
        assert 'value="asignado"' not in detail.text

        allowed_states = service.get_crm_estado_lead_options_for_update()
        target_state = next(state for state in allowed_states if state != "nuevo")

        status_response = web_client.post(
            f"/leads/{response.id_lead}/status",
            data={
                "csrf_token": csrf,
                "estado_lead": target_state,
                "return_to": "/leads?page=1",
            },
            follow_redirects=False,
        )
        assert status_response.status_code == 303

        refreshed = web_client.get(f"/leads/{response.id_lead}")
        assert target_state.replace("_", " ").title() in refreshed.text

        csrf = _extract_csrf(refreshed.text)
        comment_response = web_client.post(
            f"/leads/{response.id_lead}/comments",
            data={
                "csrf_token": csrf,
                "new_comment": "Seguimiento agregado desde integracion",
                "return_to": "/leads?page=1",
            },
            follow_redirects=False,
        )
        assert comment_response.status_code == 303

        final_detail = web_client.get(f"/leads/{response.id_lead}")
        assert "Comentario historico inicial" in final_detail.text
        assert "Seguimiento agregado desde integracion" in final_detail.text
        assert "Web CRM Follow Up" in final_detail.text
    finally:
        _cleanup(response.id_lead)


def test_web_status_update_rejects_direct_transition_to_asignado(
    web_client: TestClient, service: SolicitudService
) -> None:
    afp_id = UUID(str(service.get_catalogo_afp()[0]["id"]))
    genero_id = UUID(str(service.get_catalogo_genero()[0]["id"]))
    estado_civil_id = UUID(str(service.get_catalogo_estado_civil()[0]["id"]))
    request = RegistrarSolicitudRequest(
        persona=PersonaData(
            rut="25000005-6",
            nombre_completo="Web CRM Assigned Guard",
            email="web.crm.assigned.guard@example.com",
            telefono="+56955559999",
            fecha_nacimiento=date(1990, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=genero_id,
            estado_civil_id=estado_civil_id,
            afp_id=afp_id,
            saldo_afp=Decimal("2300000"),
            comentarios="Comentario guard",
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )
    response = service.registrar_solicitud(request)
    try:
        detail = web_client.get(f"/leads/{response.id_lead}")
        csrf = _extract_csrf(detail.text)
        denied = web_client.post(
            f"/leads/{response.id_lead}/status",
            data={"csrf_token": csrf, "estado_lead": "asignado"},
            follow_redirects=False,
        )
        assert denied.status_code == 400
        assert "No fue posible actualizar el estado" in denied.text
        refreshed = web_client.get(f"/leads/{response.id_lead}")
        assert "Asignado" not in refreshed.text
    finally:
        _cleanup(response.id_lead)


def test_web_assignment_flow_persists_and_renders_after_refresh(
    service: SolicitudService,
) -> None:
    asesores = service.get_asesores_disponibles_para_asignacion()
    assert asesores
    asesor_id = UUID(str(asesores[0]["id_asesor"]))

    app = create_web_app()
    app.state.web_service = service
    app.state.auth_provider = _FakeAuthProvider(role="executive")
    assign_client = TestClient(app)
    login_response = assign_client.post(
        "/login",
        data={"username": "diego", "password": "Secret123!"},
        follow_redirects=False,
    )
    assert login_response.status_code == 303

    afp_id = UUID(str(service.get_catalogo_afp()[0]["id"]))
    genero_id = UUID(str(service.get_catalogo_genero()[0]["id"]))
    estado_civil_id = UUID(str(service.get_catalogo_estado_civil()[0]["id"]))
    request = RegistrarSolicitudRequest(
        persona=PersonaData(
            rut="25000006-4",
            nombre_completo="Web CRM Assignment Flow",
            email="web.crm.assignment.flow@example.com",
            telefono="+56955558888",
            fecha_nacimiento=date(1990, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=genero_id,
            estado_civil_id=estado_civil_id,
            afp_id=afp_id,
            saldo_afp=Decimal("2300000"),
            comentarios="Comentario assignment flow",
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )
    response = service.registrar_solicitud(request)
    try:
        detail = assign_client.get(f"/leads/{response.id_lead}")
        assert 'name="id_asesor"' in detail.text
        assert "Selecciona un ejecutivo" in detail.text
        csrf = _extract_csrf(detail.text)

        assign_response = assign_client.post(
            f"/leads/{response.id_lead}/assign",
            data={"csrf_token": csrf, "id_asesor": str(asesor_id)},
            follow_redirects=False,
        )
        assert assign_response.status_code == 303

        refreshed = assign_client.get(f"/leads/{response.id_lead}")
        assert "Asignado" in refreshed.text
        assert 'value="asignado"' not in refreshed.text
        assert "Asignación actual" in refreshed.text

        detalle = service.get_solicitud_detalle(response.id_lead)
        assert detalle is not None
        assert detalle["estado_lead"] == "asignado"
        assert str(detalle["id_asesor"]) == str(asesor_id)
    finally:
        _cleanup(response.id_lead)


def test_web_readonly_users_cannot_mutate_leads(
    readonly_client: TestClient, service: SolicitudService
) -> None:
    afp_id = UUID(str(service.get_catalogo_afp()[0]["id"]))
    genero_id = UUID(str(service.get_catalogo_genero()[0]["id"]))
    estado_civil_id = UUID(str(service.get_catalogo_estado_civil()[0]["id"]))
    request = RegistrarSolicitudRequest(
        persona=PersonaData(
            rut="25000002-1",
            nombre_completo="Web CRM Readonly",
            email="web.crm.readonly@example.com",
            telefono="+56955558888",
            fecha_nacimiento=date(1990, 1, 1),
        ),
        solicitud=SolicitudData(
            genero_id=genero_id,
            estado_civil_id=estado_civil_id,
            afp_id=afp_id,
            saldo_afp=Decimal("2300000"),
            comentarios="Comentario readonly",
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True,
        ),
    )
    response = service.registrar_solicitud(request)
    try:
        detail = readonly_client.get(f"/leads/{response.id_lead}")
        assert detail.status_code == 200
        assert "Eliminar lead de prueba" not in detail.text
        assert "Guardar estado" not in detail.text
        assert "Agregar" not in detail.text

        denied_status = readonly_client.post(
            f"/leads/{response.id_lead}/status",
            data={"estado_lead": "contactado"},
            follow_redirects=False,
        )
        assert denied_status.status_code == 403
        assert "Esta accion no esta disponible para este usuario" in denied_status.text

        denied_comment = readonly_client.post(
            f"/leads/{response.id_lead}/comments",
            data={"new_comment": "texto"},
            follow_redirects=False,
        )
        assert denied_comment.status_code == 403
        assert "Esta accion no esta disponible para este usuario" in denied_comment.text
    finally:
        _cleanup(response.id_lead)


def test_web_board_404_for_missing_lead(web_client: TestClient) -> None:
    response = web_client.get("/leads/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert "No encontramos el lead solicitado" in response.text
