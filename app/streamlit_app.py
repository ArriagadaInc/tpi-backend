"""
Main Streamlit entrypoint for the TPI backoffice.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st

from app.components import show_database_status, show_error_message, show_header
from app.database import get_safe_error_message
from app.database.healthcheck import full_health_check
from app.services.solicitud_service import SolicitudService

st.set_page_config(
    page_title="Tu Pension Inteligente",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

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


@st.cache_resource
def get_service() -> SolicitudService:
    return SolicitudService()


def check_database_health() -> dict[str, Any]:
    return full_health_check()


def build_database_unavailable_message(health: dict[str, Any]) -> str:
    connection = health.get("connection", {})

    if connection.get("message"):
        return str(connection["message"])

    return (
        "No fue posible conectar con la base de datos. "
        "Revisa la configuracion del ambiente y vuelve a intentarlo."
    )


@st.cache_data(ttl=60)
def get_dashboard_stats() -> dict[str, Any]:
    try:
        service = get_service()
        result = service.get_solicitudes_lista(page=1, page_size=1)
        return {
            "total_solicitudes": result.get("total", 0),
            "error": None,
        }
    except Exception as exc:
        return {
            "total_solicitudes": 0,
            "error": get_safe_error_message(exc),
        }


def main() -> None:
    show_header()

    health = check_database_health()
    if not health.get("all_ready"):
        show_error_message(
            "Base de Datos No Disponible",
            build_database_unavailable_message(health),
        )
        st.stop()

    st.sidebar.markdown("---")
    st.sidebar.title("🔧 Menu")

    stats = get_dashboard_stats()
    show_database_status(
        {
            "connected": health.get("connected"),
            "total_solicitudes": stats.get("total_solicitudes", 0),
        }
    )

    st.markdown("## 📊 Panel de Control")

    if stats["error"]:
        show_error_message("Error", stats["error"])

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Solicitudes Registradas", stats["total_solicitudes"])

    with col2:
        st.metric("Estado BD", "✅ Conectada" if health.get("connected") else "❌ Desconectada")

    with col3:
        st.metric("Version MVP", "0.1.0")

    st.markdown("---")
    st.markdown("## 📖 Acerca de Esta Aplicacion")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("""
            **Tu Pension Inteligente** es un backoffice para capturar y consultar
            solicitudes de simulacion de pensiones.

            ### Caracteristicas
            - Registro de solicitudes con validacion
            - Consulta de solicitudes registradas
            - Trazabilidad y metricas
            - Enmascaramiento automatico de datos sensibles
            - Almacenamiento en PostgreSQL

            ### Validaciones automaticas
            - RUT chileno (modulo 11)
            - Telefono formato +56
            - Email valido
            - Fecha no futura
            - Datos requeridos obligatorios
            """)

    with col2:
        st.markdown("""
            ### Informacion tecnica
            - **Lenguaje**: Python 3.12
            - **Framework**: Streamlit 1.28+
            - **Base de Datos**: PostgreSQL
            - **Driver**: Psycopg 3
            - **Validacion**: Pydantic 2

            ### Limitaciones MVP
            - Sin autenticacion
            - Sin edicion de solicitudes
            - Sin auditoria de cambios
            - Despliegue productivo pendiente
            """)

    st.markdown("---")
    st.markdown("## 🚀 Comenzar")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.info("""
            ### 📝 Registrar Solicitud
            Ve a la pagina de registro para capturar una nueva solicitud de simulacion.
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
            ### 📈 Trazabilidad y Metricas
            Visualiza estadisticas y analisis de las solicitudes.
            """)
        st.page_link("pages/3_trazabilidad.py", label="Ir a Trazabilidad", icon="📈")

    st.markdown("---")
    footer_col1, footer_col2, footer_col3 = st.columns(3)

    with footer_col1:
        st.caption("**Version**: 0.1.0 MVP")

    with footer_col2:
        st.caption(f"**Ultima actualizacion**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    with footer_col3:
        st.caption("**Status**: En Desarrollo")


if __name__ == "__main__":
    main()
