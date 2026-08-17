"""Private Streamlit entrypoint for operational TPI backoffice features."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st

from app.auth import require_authenticated_user
from app.components import show_database_status, show_error_message, show_header
from app.database import get_safe_error_message
from app.database.healthcheck import full_health_check
from app.runtime import initialize_runtime, log_health_status, run_guarded
from app.services.solicitud_service import SolicitudService

st.set_page_config(
    page_title="TPI Backoffice",
    page_icon="B",
    layout="wide",
    initial_sidebar_state="expanded",
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
    return "No fue posible conectar con la base de datos. Revisa la configuracion del ambiente."


@st.cache_data(ttl=60)
def get_dashboard_stats() -> dict[str, Any]:
    try:
        result = get_service().get_solicitudes_lista(page=1, page_size=1)
        return {"total_solicitudes": result.get("total", 0), "error": None}
    except Exception as exc:
        return {"total_solicitudes": 0, "error": get_safe_error_message(exc)}


def main() -> None:
    logger = initialize_runtime("app.backoffice_app")
    require_authenticated_user()
    show_header()

    health = check_database_health()
    log_health_status(health, logger)
    if not health.get("all_ready"):
        show_error_message(
            "Base de datos no disponible", build_database_unavailable_message(health)
        )
        st.stop()

    stats = get_dashboard_stats()
    show_database_status(
        {
            "connected": health.get("connected"),
            "total_solicitudes": stats.get("total_solicitudes", 0),
        }
    )
    st.title("Panel de control")
    if stats["error"]:
        show_error_message("Error", stats["error"])

    col1, col2, col3 = st.columns(3)
    col1.metric("Solicitudes registradas", stats["total_solicitudes"])
    col2.metric("Estado BD", "Conectada" if health.get("connected") else "Desconectada")
    col3.metric("Version", "MVP")

    st.markdown("## Operacion privada")
    st.page_link("pages/2_solicitudes_registradas.py", label="Consultar solicitudes")
    st.page_link("pages/3_trazabilidad.py", label="Ver trazabilidad")
    st.caption(f"Ultima actualizacion: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    run_guarded(main, page_name="app.backoffice_app")
