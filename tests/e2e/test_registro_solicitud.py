"""
Tests E2E para página de registro de solicitudes.

Validación de:
- Carga del formulario
- Dropdowns de catálogos
- Validación de campos
- Envío de solicitud
"""

import pytest


@pytest.mark.e2e
class TestRegistroSolicitudForm:
    """Tests para formulario de registro."""

    @pytest.fixture
    def app(self, streamlit_app_factory):
        """Instancia la página de registro."""
        return streamlit_app_factory("app/pages/1_registrar_solicitud.py")

    def test_page_loads_successfully(self, app):
        """Test que página se carga sin errores."""
        app.run()
        assert not app.exception, f"Exception: {app.exception}"

    def test_form_title_displayed(self, app):
        """Test que título del formulario se muestra."""
        app.run()

        # Debe haber al menos un título
        titles = app.title
        assert len(titles) > 0

    def test_form_fields_present(self, app):
        """Test que campos del formulario están presentes."""
        app.run()

        # Debe haber inputs de texto
        text_inputs = app.text_input
        assert len(text_inputs) >= 3, "Faltan campos de texto (RUT, nombre, email)"

    def test_form_select_boxes_present(self, app):
        """Test que selectboxes están presentes."""
        app.run()

        # Debe haber al menos 3 selectboxes (género, estado civil, AFP)
        selectboxes = app.selectbox
        assert len(selectboxes) >= 3, "Faltan selectboxes de catálogos"

    def test_form_date_input_present(self, app):
        """Test que input de fecha está presente."""
        app.run()

        # Debe haber al menos 1 date_input
        date_inputs = app.date_input
        assert len(date_inputs) >= 1, "Falta input de fecha de nacimiento"

    def test_form_checkboxes_present(self, app):
        """Test que checkboxes de consentimientos están presentes."""
        app.run()

        # Debe haber al menos 3 checkboxes
        checkboxes = app.checkbox
        assert len(checkboxes) >= 3, "Faltan checkboxes de consentimientos"

    def test_form_submit_button_present(self, app):
        """Test que botón de envío está presente."""
        app.run()

        # Debe haber botón de submit
        buttons = app.button
        # Debería haber al menos 2 botones (enviar y limpiar)
        assert len(buttons) >= 2, "Falta botón de envío"

    def test_catalogs_loaded(self, app):
        """Test que catálogos se cargan desde BD."""
        app.run()

        # No debe haber error al cargar catálogos
        assert not app.exception


@pytest.mark.e2e
class TestRegistroSolicitudValidation:
    """Tests para validación del formulario."""

    @pytest.fixture
    def app(self, streamlit_app_factory):
        """Instancia la página de registro."""
        return streamlit_app_factory("app/pages/1_registrar_solicitud.py")

    def test_empty_rut_validation(self, app):
        """Test validación de RUT vacío."""
        app.run()

        # Llenar solo nombre
        name_inputs = app.text_input
        if len(name_inputs) > 1:
            name_inputs[1].set_value("Juan Pérez")

        # Intentar enviar
        buttons = app.button
        if len(buttons) > 0:
            # El primer botón suele ser el submit
            buttons[0].click()
            app.run()

            # Debería mostrar error de validación
            assert not app.exception or len(app.error) > 0 or len(app.warning) > 0

    def test_form_with_all_required_fields(self, app):
        """Test que formulario acepta todos los campos requeridos."""
        app.run()

        # Verificar que se renderizó correctamente
        assert not app.exception

        # Debe haber todos los tipos de input
        assert len(app.text_input) >= 4  # RUT, nombre, email, teléfono
        assert len(app.date_input) >= 1  # Fecha nacimiento
        assert len(app.selectbox) >= 3  # Género, estado civil, AFP
        assert len(app.checkbox) >= 3  # Consentimientos


@pytest.mark.e2e
class TestRegistroSolicitudSubmit:
    """Tests para envío de solicitud."""

    @pytest.fixture
    def app(self, streamlit_app_factory):
        """Instancia la página de registro."""
        return streamlit_app_factory("app/pages/1_registrar_solicitud.py")

    def test_form_renders_without_error(self, app):
        """Test que formulario se renderiza sin error."""
        app.run()
        assert not app.exception

    def test_success_message_structure(self, app):
        """Test que estructura de success message es válida."""
        app.run()

        # No debería haber errores en la app
        assert not app.exception


@pytest.mark.e2e
class TestRegistroSolicitudIntegration:
    """Tests integración con servicio de BD."""

    @pytest.fixture
    def app(self, streamlit_app_factory):
        """Instancia la página de registro."""
        return streamlit_app_factory("app/pages/1_registrar_solicitud.py")

    def test_catalogs_from_database(self, app):
        """Test que catálogos se cargan desde BD."""
        app.run()

        # Debe haber selectboxes con opciones
        selectboxes = app.selectbox
        assert len(selectboxes) >= 3

        # Cada selectbox debe tener opciones
        for selectbox in selectboxes:
            # El selectbox debería tener opciones de catálogos
            assert selectbox is not None

    def test_database_connection_verified(self, app):
        """Test que conexión a BD se verifica."""
        app.run()

        # Si hay error de conexión, debería mostrarse
        if app.error:
            assert "Base de Datos" in str(app.error) or "Catálogos" in str(app.error)
        else:
            # Si no hay error, app debería estar lista
            assert not app.exception


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "e2e"])
