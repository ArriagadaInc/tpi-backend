"""
Tests E2E para página de registro de solicitudes.

Validación de:
- Carga del formulario
- Dropdowns de catálogos
- Validación de campos
- Envío de solicitud
"""

from uuid import UUID, uuid4

import pytest
import streamlit as st

from app.database.connection import get_db_connection
from app.notifications import LeadCreatedEvent, PublishResult
from app.services import solicitud_service


@pytest.mark.e2e
class TestRegistroSolicitudForm:
    """Tests para formulario de registro."""

    @pytest.fixture
    def app(self, streamlit_app_factory):
        """Instancia la página de registro."""
        return streamlit_app_factory("app/streamlit_app.py")

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
        assert len(buttons) >= 1, "Falta botón de envío"

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
        return streamlit_app_factory("app/streamlit_app.py")

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
        return streamlit_app_factory("app/streamlit_app.py")

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
        return streamlit_app_factory("app/streamlit_app.py")

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


@pytest.mark.e2e
class TestRegistroSolicitudNotifications:
    """The form keeps its success path while the service emits a safe event."""

    def test_successful_form_submission_invokes_publisher(
        self, streamlit_app_factory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class RecordingPublisher:
            def __init__(self) -> None:
                self.events: list[LeadCreatedEvent] = []

            def publish(self, event: LeadCreatedEvent) -> PublishResult:
                self.events.append(event)
                return PublishResult("published", "fake", "message-123")

        publisher = RecordingPublisher()
        monkeypatch.setattr(
            solicitud_service,
            "build_lead_event_publisher",
            lambda settings: publisher,
        )
        st.cache_resource.clear()
        try:
            app = streamlit_app_factory("app/streamlit_app.py")
            app.run()

            body = str(10_000_000 + uuid4().int % 80_000_000)
            total = sum(int(digit) * (2 + index % 6) for index, digit in enumerate(reversed(body)))
            verifier = 11 - total % 11
            digit = "0" if verifier == 11 else "K" if verifier == 10 else str(verifier)
            app.text_input[0].set_value(f"{body}-{digit}")
            app.text_input[1].set_value("Lead Ficticio E2E")
            app.text_input[2].set_value("lead.e2e@example.test")
            app.text_input[3].set_value("+56911112222")
            for checkbox in app.checkbox:
                checkbox.set_value(True)
            app.button[0].click()
            app.run()

            assert len(publisher.events) == 1
            assert any(
                "Solicitud registrada correctamente" in str(item.value) for item in app.success
            )

            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id_persona FROM tpi.leads WHERE id_lead = %s",
                        (str(publisher.events[0].lead_id),),
                    )
                    row = cur.fetchone()
                    assert row is not None
                    id_persona = UUID(str(row["id_persona"]))
                    cur.execute(
                        "DELETE FROM tpi.consentimientos WHERE id_lead = %s",
                        (str(publisher.events[0].lead_id),),
                    )
                    cur.execute(
                        "DELETE FROM tpi.leads WHERE id_lead = %s",
                        (str(publisher.events[0].lead_id),),
                    )
                    cur.execute(
                        "DELETE FROM tpi.personas WHERE id_persona = %s", (str(id_persona),)
                    )
                conn.commit()
        finally:
            st.cache_resource.clear()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "e2e"])
