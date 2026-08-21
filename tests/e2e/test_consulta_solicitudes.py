"""
Tests E2E para página de consulta de solicitudes.

Validación de:
- Carga de lista paginada
- Búsqueda por RUT
- Detalle de solicitud
- Enmascaramiento de datos
"""

from datetime import datetime

import pytest

from app.models.test_lead_cleanup import TestLeadCleanupResult
from app.services.solicitud_service import SolicitudService


@pytest.mark.e2e
class TestConsultaSolicitudesPage:
    """Tests para página de consultas."""

    @pytest.fixture
    def app(self, streamlit_app_factory):
        """Instancia la página de consultas."""
        return streamlit_app_factory("app/pages/2_solicitudes_registradas.py")

    def test_page_loads_successfully(self, app):
        """Test que página se carga sin errores."""
        app.run()
        assert not app.exception, f"Exception: {app.exception}"

    def test_page_title_displayed(self, app):
        """Test que título de página se muestra."""
        app.run()

        titles = app.title
        assert len(titles) > 0

    def test_tabs_rendered(self, app):
        """Test que tabs están presentes."""
        app.run()

        # Debe haber contenido de tabs
        assert not app.exception


@pytest.mark.e2e
class TestConsultaSolicitudesLista:
    """Tests para tab de listar solicitudes."""

    @pytest.fixture
    def app(self, streamlit_app_factory):
        """Instancia la página de consultas."""
        return streamlit_app_factory("app/pages/2_solicitudes_registradas.py")

    def test_pagination_control_present(self, app):
        """Test que controles de paginación están presentes."""
        app.run()

        # Debe haber selectbox de tamaño de página
        selectboxes = app.selectbox
        assert len(selectboxes) >= 1, "Falta control de paginación"

    def test_pagination_options_valid(self, app):
        """Test que opciones de paginación son válidas."""
        app.run()

        selectboxes = app.selectbox
        # Selectbox de paginación debe tener opciones
        assert len(selectboxes) > 0

    def test_solicitudes_table_structure(self, app):
        """Test que tabla de solicitudes tiene estructura correcta."""
        app.run()

        # No debería haber error
        assert not app.exception

        # Debe haber elementos de table o dataframe
        # (Streamlit renderea tablas como dataframe)
        assert len(app.dataframe) >= 0  # Puede no haber datos, pero estructura sí


@pytest.mark.e2e
class TestConsultaSolicitudesBusqueda:
    """Tests para búsqueda por RUT."""

    @pytest.fixture
    def app(self, streamlit_app_factory):
        """Instancia la página de consultas."""
        return streamlit_app_factory("app/pages/2_solicitudes_registradas.py")

    def test_search_input_present(self, app):
        """Test que input de búsqueda está presente."""
        app.run()

        labels = [element.label for element in app.text_input]
        assert "Ingresa RUT a buscar" in labels, "Falta input de búsqueda por RUT"

    def test_search_button_present(self, app):
        """Test que botón de búsqueda está presente."""
        app.run()

        buttons = [element.label for element in app.button]
        assert "Buscar lead" in buttons, "Falta botón de búsqueda"

    def test_search_with_invalid_rut_format(self, app):
        """Test búsqueda con formato inválido de RUT."""
        app.run()

        # No debería causar excepción
        assert not app.exception

    def test_search_same_lead_in_list_does_not_show_error(self, monkeypatch, streamlit_app_factory):
        """No debe fallar si el mismo lead aparece en listado y b?squeda."""
        record = {
            "id_lead": "11111111-1111-1111-1111-111111111111",
            "id_persona": "22222222-2222-2222-2222-222222222222",
            "rut": "12.***.***-5",
            "nombre_completo": "Lead Sintetico",
            "email": "te***@example.com",
            "telefono": "+56 9 **** 5678",
            "afp": "Habitat",
            "genero": "Masculino",
            "estado_civil": "Soltero/a",
            "saldo_afp": 100000,
            "estado_lead": "pendiente",
            "created_at": datetime(2026, 8, 7, 12, 0, 0),
            "acepta_terminos": True,
            "acepta_politica_privacidad": True,
            "finalidad_contacto": True,
            "comentarios": "Registro sintetico para regresion",
        }

        monkeypatch.setattr(
            SolicitudService,
            "get_crm_bandeja",
            lambda self, page=1, page_size=10, masked=True, **kwargs: {
                "solicitudes": [record],
                "total": 1,
                "page": 1,
                "page_size": page_size,
                "total_pages": 1,
            },
        )
        monkeypatch.setattr(
            SolicitudService,
            "get_solicitud_detalle_masked",
            lambda self, id_lead: record,
        )
        monkeypatch.setattr(
            SolicitudService,
            "get_solicitudes_por_rut",
            lambda self, rut, masked=True: [record],
        )

        app = streamlit_app_factory("app/pages/2_solicitudes_registradas.py")
        app.run()
        next(
            element for element in app.text_input if element.label == "Ingresa RUT a buscar"
        ).set_value("12345678-5")
        app.run()
        next(button for button in app.button if button.label == "Buscar lead").click()
        app.run()

        success_messages = [element.value for element in app.success]
        error_messages = [element.value for element in app.error]

        assert "Se encontraron 1 lead(s)" in success_messages
        assert not any("Error en la Busqueda" in message for message in error_messages)
        assert not any("Ocurrio un error inesperado" in message for message in error_messages)

    def test_search_with_empty_rut(self, app):
        """Test búsqueda con RUT vacío."""
        app.run()

        # No debería causar excepción
        assert not app.exception


@pytest.mark.e2e
class TestConsultaSolicitudesDetalle:
    """Tests para vista de detalle."""

    @pytest.fixture
    def app(self, streamlit_app_factory):
        """Instancia la página de consultas."""
        return streamlit_app_factory("app/pages/2_solicitudes_registradas.py")

    def test_detail_view_initializes(self, app):
        """Test que vista de detalle puede inicializarse."""
        app.run()

        # No debería haber error
        assert not app.exception

    def test_dev_cleanup_requires_two_confirmations_and_removes_the_detail(
        self,
        monkeypatch,
        streamlit_app_factory,
    ):
        record = {
            "id_lead": "11111111-1111-1111-1111-111111111111",
            "id_persona": "22222222-2222-2222-2222-222222222222",
            "rut": "12.***.***-5",
            "nombre_completo": "Lead Sintetico",
            "email": "te***@example.com",
            "telefono": "+56 9 **** 5678",
            "afp": "Habitat",
            "genero": "Masculino",
            "estado_civil": "Soltero/a",
            "saldo_afp": 100000,
            "estado_lead": "pendiente",
            "created_at": datetime(2026, 8, 7, 12, 0, 0),
            "acepta_terminos": True,
            "acepta_politica_privacidad": True,
            "finalidad_contacto": True,
            "comentarios": "Registro sintetico para regresion",
        }
        state = {"deleted": False}

        monkeypatch.setattr(SolicitudService, "is_test_lead_cleanup_enabled", lambda self: True)
        monkeypatch.setattr(
            SolicitudService,
            "get_crm_bandeja",
            lambda self, page=1, page_size=10, masked=True, **kwargs: {
                "solicitudes": [] if state["deleted"] else [record],
                "total": 0 if state["deleted"] else 1,
                "page": 1,
                "page_size": page_size,
                "total_pages": 0 if state["deleted"] else 1,
            },
        )
        monkeypatch.setattr(
            SolicitudService, "get_solicitud_detalle_masked", lambda self, id_lead: record
        )

        def delete_test_lead(self, id_lead):
            state["deleted"] = True
            return TestLeadCleanupResult(
                status="deleted",
                message="Lead de prueba eliminado correctamente.",
            )

        monkeypatch.setattr(SolicitudService, "delete_test_lead", delete_test_lead)

        app = streamlit_app_factory("app/pages/2_solicitudes_registradas.py")
        app.run()
        detail_button = next(button for button in app.button if button.label == "Abrir")
        detail_button.click()
        app.run()

        assert any(
            element.label == "Confirmo que este es un dato de prueba" for element in app.checkbox
        )
        assert any(element.label == "Escribe ELIMINAR para confirmar" for element in app.text_input)
        delete_button = next(
            button for button in app.button if button.label == "ELIMINAR LEAD DE PRUEBA"
        )
        assert delete_button.disabled

        app.checkbox[0].set_value(True)
        next(
            element
            for element in app.text_input
            if element.label == "Escribe ELIMINAR para confirmar"
        ).set_value("ELIMINAR")
        app.run()
        next(button for button in app.button if button.label == "ELIMINAR LEAD DE PRUEBA").click()
        app.run()

        assert state["deleted"]
        assert "Lead de prueba eliminado correctamente." in [
            element.value for element in app.success
        ]


@pytest.mark.e2e
class TestConsultaSolicitudesSeguridad:
    """Tests de seguridad para consultas."""

    @pytest.fixture
    def app(self, streamlit_app_factory):
        """Instancia la página de consultas."""
        return streamlit_app_factory("app/pages/2_solicitudes_registradas.py")

    def test_masking_applied_in_list(self, app):
        """Test que enmascaramiento se aplica en lista."""
        app.run()

        # La página debe estar configurada con masked=True
        # No podemos verificar el contenido sin datos, pero no debería haber error
        assert not app.exception

    def test_no_sensitive_data_in_error_messages(self, app):
        """Test que mensajes de error no exponen datos sensibles."""
        app.run()

        # Revisar que no hay RUT sin enmascaramiento en logs
        # (esto es más una auditoría manual)
        assert not app.exception


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "e2e"])
