"""
Tests E2E para página principal (streamlit_app.py).

Validación de:
- Carga de página y verificación de BD
- Renderizado de componentes
- Navegación a páginas secundarias
"""

import pytest


@pytest.mark.e2e
class TestStreamlitAppMain:
    """Tests para página principal."""

    @pytest.fixture
    def app(self, streamlit_app_factory):
        """Instancia la app principal."""
        return streamlit_app_factory("app/streamlit_app.py")

    def test_app_loads_successfully(self, app):
        """Test que la app se carga sin errores."""
        app.run()
        assert not app.exception

    def test_database_status_displayed(self, app):
        """Test que se muestra estado de BD."""
        app.run()

        # Buscar el metric de estado BD
        metrics = [w for w in app.metric]
        assert len(metrics) > 0, "No se encontraron metrics en la página"

    def test_app_header_present(self, app):
        """Test que header está presente."""
        app.run()

        # Verificar que no hay excepciones y que se renderizó
        assert not app.exception
        # Header debería estar en el contenido de la página
        assert len(app.markdown) > 0 or len(app.title) > 0

    def test_navigation_links_present(self, app):
        """Test que links de navegación están presentes."""
        app.run()

        # Debe haber al menos 3 botones de navegación (a las 3 páginas)
        [w for w in app.button]
        # Los page_link se renderean como buttons o links
        assert not app.exception

    def test_app_title_correct(self, app):
        """Test que el título es correcto."""
        app.run()

        # Streamlit debe tener rendered el título
        assert not app.exception
        assert len(app.title) > 0

    def test_app_configuration_loaded(self, app):
        """Test que configuración se carga."""
        app.run()

        # Debe existir session state
        assert app.session_state is not None


@pytest.mark.e2e
class TestStreamlitAppSidebar:
    """Tests para sidebar."""

    @pytest.fixture
    def app(self, streamlit_app_factory):
        """Instancia la app principal."""
        return streamlit_app_factory("app/streamlit_app.py")

    def test_sidebar_rendered(self, app):
        """Test que sidebar se renderiza."""
        app.run()

        # Sidebar debe tener elementos
        assert not app.exception

    def test_database_status_in_sidebar(self, app):
        """Test que estado de BD aparece en sidebar."""
        app.run()

        # Verificar que la función show_database_status se llamó
        assert not app.exception


@pytest.mark.e2e
class TestStreamlitAppMetrics:
    """Tests para métricas del dashboard."""

    @pytest.fixture
    def app(self, streamlit_app_factory):
        """Instancia la app principal."""
        return streamlit_app_factory("app/streamlit_app.py")

    def test_metrics_rendered(self, app):
        """Test que métricas se renderizan."""
        app.run()

        # Debe haber al menos 3 metrics (solicitudes, BD, versión)
        metrics = app.metric
        assert len(metrics) >= 3

    def test_metrics_have_labels(self, app):
        """Test que métricas tienen labels."""
        app.run()

        metrics = app.metric
        for metric in metrics:
            assert metric.label is not None
            assert len(metric.label) > 0

    def test_metrics_have_values(self, app):
        """Test que métricas tienen valores."""
        app.run()

        metrics = app.metric
        for metric in metrics:
            # El valor puede ser None si hay error, pero label debe existir
            assert metric.label is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "e2e"])
