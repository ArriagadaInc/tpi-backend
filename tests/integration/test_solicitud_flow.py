"""Pruebas de integración para flujo de solicitudes."""

import pytest
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.database.healthcheck import full_health_check
from app.models.solicitud import (
    ConsentimientosData,
    PersonaData,
    RegistrarSolicitudRequest,
    SolicitudData,
)
from app.services.solicitud_service import SolicitudService

pytestmark = pytest.mark.integration


@pytest.fixture
def service():
    """Fixture que proporciona el servicio."""
    return SolicitudService()


@pytest.fixture(scope="session", autouse=True)
def verify_database():
    """Verifica que la BD esté disponible antes de ejecutar tests."""
    health = full_health_check()
    if not health.get("all_ready"):
        pytest.skip("Base de datos no disponible para tests de integración")


class TestSolicitudFlow:
    """Pruebas del flujo completo de solicitud."""

    def test_registrar_solicitud_completa(self, service):
        """Test de integración: registra solicitud completa en BD."""
        # Obtener un AFP válido para usar en el test
        afps = service.get_catalogo_afp()
        assert len(afps) > 0, "Debe haber al menos un AFP para el test"
        afp_id = UUID(str(afps[0]["id_afp"]))

        # Obtener un género válido
        generos = service.get_catalogo_genero()
        assert len(generos) > 0, "Debe haber al menos un género para el test"
        genero_id = UUID(str(generos[0]["id_genero"]))

        # Obtener un estado civil válido
        estados = service.get_catalogo_estado_civil()
        assert len(estados) > 0, "Debe haber al menos un estado civil para el test"
        estado_civil_id = UUID(str(estados[0]["id_estado_civil"]))

        # Crear request con datos de test
        request = RegistrarSolicitudRequest(
            persona=PersonaData(
                rut="19999999-9",
                nombre_completo="Test User",
                email="test@example.com",
                telefono="+56912345678",
                fecha_nacimiento=date(1990, 1, 1),
            ),
            solicitud=SolicitudData(
                genero_id=genero_id,
                estado_civil_id=estado_civil_id,
                afp_id=afp_id,
                saldo_afp=Decimal("100000.00"),
                comentarios="Test solicitud de integración",
            ),
            consentimientos=ConsentimientosData(
                acepta_terminos=True,
                acepta_politica_privacidad=True,
                finalidad_contacto=True,
            ),
        )

        # Registrar solicitud
        response = service.registrar_solicitud(request)

        # Verificaciones
        assert response.id_lead is not None
        assert response.id_persona is not None
        assert response.rut == "19999999-9"
        assert response.nombre_completo == "Test User"
        assert response.estado_lead == "pendiente"
        assert "exitosamente" in response.mensaje.lower()

    def test_get_catalogo_afp(self, service):
        """Obtiene listado de AFP activos."""
        afps = service.get_catalogo_afp()
        assert len(afps) > 0
        assert all("id_afp" in afp for afp in afps)
        assert all("descripcion" in afp for afp in afps)

    def test_get_catalogo_genero(self, service):
        """Obtiene listado de géneros activos."""
        generos = service.get_catalogo_genero()
        assert len(generos) > 0
        assert all("id_genero" in genero for genero in generos)
        assert all("descripcion" in genero for genero in generos)

    def test_get_catalogo_estado_civil(self, service):
        """Obtiene listado de estados civiles activos."""
        estados = service.get_catalogo_estado_civil()
        assert len(estados) > 0
        assert all("id_estado_civil" in estado for estado in estados)
        assert all("descripcion" in estado for estado in estados)

    def test_get_solicitudes_lista_paginada(self, service):
        """Obtiene lista paginada de solicitudes."""
        result = service.get_solicitudes_lista(page=1, page_size=10, masked=True)

        assert "solicitudes" in result
        assert "total" in result
        assert "page" in result
        assert "page_size" in result
        assert "total_pages" in result

        assert result["page"] == 1
        assert result["page_size"] == 10
        assert result["total"] >= 0

    def test_solicitud_detalle_masked(self, service):
        """Obtiene detalle de solicitud con enmascaramiento."""
        # Obtener primera solicitud
        result = service.get_solicitudes_lista(page=1, page_size=1)
        if result["total"] == 0:
            pytest.skip("No hay solicitudes para consultar")

        # Obtener detalle enmascarado
        solicitud = result["solicitudes"][0]
        if "id_lead" not in solicitud:
            pytest.skip("Solicitud sin id_lead")

        id_lead = UUID(str(solicitud["id_lead"]))
        detalle = service.get_solicitud_detalle_masked(id_lead)

        assert detalle is not None
        # Verificar que hay enmascaramiento (debería contener ***)
        # Si hay un RUT, debería estar enmascarado
        if "rut" in detalle:
            assert "***" in detalle["rut"] or len(detalle["rut"]) < 11

    def test_registrar_solicitud_con_ids_invalidos_falla(self, service):
        """Test: insertar con ID de catálogo inválido falla."""
        # UUID inválido (no existe en catálogo)
        invalid_uuid = UUID("00000000-0000-0000-0000-000000000000")

        request = RegistrarSolicitudRequest(
            persona=PersonaData(
                rut="19888888-8",
                nombre_completo="Test Invalid",
                email="invalid@test.com",
                telefono="+56912345678",
                fecha_nacimiento=date(1990, 1, 1),
            ),
            solicitud=SolicitudData(
                genero_id=invalid_uuid,  # ← inválido
                estado_civil_id=invalid_uuid,
                afp_id=invalid_uuid,
                saldo_afp=Decimal("100000.00"),
                comentarios="Test con IDs inválidos",
            ),
            consentimientos=ConsentimientosData(
                acepta_terminos=True,
                acepta_politica_privacidad=True,
                finalidad_contacto=True,
            ),
        )

        # Debe lanzar excepción
        with pytest.raises(ValueError):
            service.registrar_solicitud(request)

    def test_get_solicitudes_por_rut(self, service):
        """Obtiene solicitudes de una persona por RUT."""
        # Usar un RUT que sabemos que existe (del test anterior)
        solicitudes = service.get_solicitudes_por_rut("19999999-9", masked=True)

        # Debería retornar lista (puede estar vacía si el test anterior no corrió)
        assert isinstance(solicitudes, list)

        # Si hay solicitudes, verificar estructura
        if len(solicitudes) > 0:
            solicitud = solicitudes[0]
            assert "id_lead" in solicitud
            assert "rut" in solicitud
            assert "nombre_completo" in solicitud


class TestValidationRules:
    """Pruebas de reglas de validación de negocio."""

    def test_personas_con_rut_duplicado_reutilizan_id(self, service):
        """Test: insertar persona con RUT existente reutiliza ID."""
        from app.database.connection import get_db_connection
        from app.repositories import SolicitudRepository

        # Crear una persona
        persona1 = PersonaData(
            rut="18777777-7",
            nombre_completo="Primera Persona",
            email="primera@test.com",
            telefono="+56912345678",
            fecha_nacimiento=date(1990, 1, 1),
        )

        repo = SolicitudRepository()
        id_persona1 = repo.create_persona(persona1)

        # Intentar crear la misma persona nuevamente
        persona2 = PersonaData(
            rut="18777777-7",  # ← mismo RUT
            nombre_completo="Primera Persona",  # ← mismo nombre
            email="primera@test.com",
            telefono="+56912345678",
            fecha_nacimiento=date(1990, 1, 1),
        )

        id_persona2 = repo.create_persona(persona2)

        # Deben ser el mismo ID
        assert id_persona1 == id_persona2

    def test_consentimientos_todos_obligatorios(self, service):
        """Test: rechaza si faltan consentimientos."""
        afps = service.get_catalogo_afp()
        generos = service.get_catalogo_genero()
        estados = service.get_catalogo_estado_civil()

        if not (afps and generos and estados):
            pytest.skip("Catálogos no disponibles")

        # Crear request SIN aceptar términos (debería fallar en Pydantic)
        with pytest.raises(Exception):  # ValueError de Pydantic
            request = RegistrarSolicitudRequest(
                persona=PersonaData(
                    rut="18666666-6",
                    nombre_completo="Test",
                    email="test@test.com",
                    telefono="+56912345678",
                    fecha_nacimiento=date(1990, 1, 1),
                ),
                solicitud=SolicitudData(
                    genero_id=UUID(str(generos[0]["id_genero"])),
                    estado_civil_id=UUID(str(estados[0]["id_estado_civil"])),
                    afp_id=UUID(str(afps[0]["id_afp"])),
                    saldo_afp=Decimal("100000.00"),
                    comentarios="Test",
                ),
                consentimientos=ConsentimientosData(
                    acepta_terminos=False,  # ← falta aceptación
                    acepta_politica_privacidad=True,
                    finalidad_contacto=True,
                ),
            )
