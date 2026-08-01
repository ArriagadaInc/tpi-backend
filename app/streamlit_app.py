"""
Página principal de Tu Pensión Inteligente Back-office MVP.

Esta es la aplicación Streamlit principal que:
- Verifica la conexión a base de datos
- Muestra estadísticas generales
- Proporciona navegación a otras páginas
"""

from datetime import datetime

import streamlit as st

from app.components import show_database_status, show_error_message, show_header
from app.database.healthcheck import full_health_check
from app.services.solicitud_service import SolicitudService

# ============================================================================
# CONFIGURACIÓN DE STREAMLIT
# ============================================================================

st.set_page_config(
    page_title="Tu Pensión Inteligente",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Aplicar estilos CSS
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .stat-box {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================


@st.cache_resource
def get_service() -> SolicitudService:
    """Obtiene instancia del servicio (caché)."""
    return SolicitudService()


def check_database_health() -> dict:
    """Verifica la salud de la base de datos."""
    return full_health_check()


@st.cache_data(ttl=60)  # Cache de 60 segundos
def get_dashboard_stats():
    """Obtiene estadísticas para el dashboard."""
    try:
        service = get_service()
        result = service.get_solicitudes_lista(page=1, page_size=1)

        return {
            "total_solicitudes": result.get("total", 0),
            "error": None,
        }
    except Exception as e:
        return {
            "total_solicitudes": 0,
            "error": str(e),
        }


# ============================================================================
# PÁGINA PRINCIPAL
# ============================================================================


def main():
    """Función principal de la aplicación."""

    # Header
    show_header()

    # Verificar BD al cargar
    health = check_database_health()

    if not health.get("all_ready"):
        show_error_message(
            "Base de Datos No Disponible",
            "No se pudo conectar a la base de datos. Por favor, verifica que PostgreSQL esté ejecutándose y que las variables de entorno estén configuradas correctamente.",
        )
        st.stop()

    # Sidebar
    st.sidebar.markdown("---")
    st.sidebar.title("🔧 Menú")

    # Mostrar estado de BD en sidebar
    show_database_status(
        {
            "connected": health.get("connected"),
            "total_solicitudes": get_dashboard_stats().get("total_solicitudes", 0),
        }
    )

    # Contenido principal
    st.markdown("## 📊 Panel de Control")

    # Estadísticas
    stats = get_dashboard_stats()
    if stats["error"]:
        show_error_message("Error", f"No se pudieron cargar las estadísticas: {stats['error']}")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Solicitudes Registradas", stats["total_solicitudes"])

    with col2:
        st.metric(
            "Estado BD",
            "✅ Conectada" if health.get("connected") else "❌ Desconectada",
        )

    with col3:
        st.metric("Versión MVP", "0.1.0")

    # Sección de información
    st.markdown("---")
    st.markdown("## 📖 Acerca de Esta Aplicación")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("""
        **Tu Pensión Inteligente** es un prototipo funcional de back-office para capturar y
        consultar solicitudes de simulación de pensiones.

        ### Características:
        - ✅ Registro de solicitudes con validación
        - ✅ Consulta de solicitudes registradas
        - ✅ Trazabilidad y métricas
        - ✅ Enmascaramiento automático de datos sensibles
        - ✅ Almacenamiento en PostgreSQL

        ### Validaciones Automáticas:
        - RUT chileno (módulo 11)
        - Teléfono formato +56
        - Email válido
        - Fecha no futura
        - Datos requeridos obligatorios
        """)

    with col2:
        st.markdown("""
        ### Información Técnica
        - **Lenguaje**: Python 3.12
        - **Framework**: Streamlit 1.28+
        - **Base de Datos**: PostgreSQL
        - **ORM**: Psycopg 3.1+
        - **Validación**: Pydantic 2.0+

        ### Limitaciones MVP
        - ⚠️ Sin autenticación
        - ⚠️ Sin edición de solicitudes
        - ⚠️ Sin auditoría de cambios
        - ⚠️ Solo demostración local
        """)

    # Navegación
    st.markdown("---")
    st.markdown("## 🚀 Comenzar")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.info("""
        ### 📝 Registrar Solicitud
        Ve a la página de registro para capturar una nueva solicitud de simulación.
        """)
        st.page_link("pages/1_registrar_solicitud.py", label="Ir a Registro", icon="📝")

    with col2:
        st.info("""
        ### 🔍 Consultar Solicitudes
        Busca y visualiza todas las solicitudes registradas en el sistema.
        """)
        st.page_link("pages/2_solicitudes_registradas.py", label="Ir a Consultas", icon="🔍")

    with col3:
        st.info("""
        ### 📈 Trazabilidad y Métricas
        Visualiza estadísticas y análisis de las solicitudes.
        """)
        st.page_link("pages/3_trazabilidad.py", label="Ir a Trazabilidad", icon="📈")

    # Footer
    st.markdown("---")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.caption("**Version**: 0.1.0 MVP")

    with col2:
        st.caption(f"**Última actualización**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    with col3:
        st.caption("**Status**: ✅ En Desarrollo")


if __name__ == "__main__":
    main()
