"""Componentes reutilizables de UI para Streamlit."""

from typing import Any

import streamlit as st


def show_header():
    """Muestra el header de la aplicación."""
    st.markdown("---")
    col1, col2, col3 = st.columns([2, 3, 1])

    with col1:
        st.image("", width=100) if False else None  # Placeholder para logo

    with col2:
        st.title("💼 Tu Pensión Inteligente")
        st.caption("Back-office MVP - Simulador de pensiones")

    with col3:
        st.caption("v0.1.0 MVP")

    st.markdown("---")


def show_success_message(title: str, message: str, icon: str = "✅"):
    """Muestra un mensaje de éxito."""
    st.success(f"{icon} **{title}**\n{message}")


def show_error_message(title: str, message: str, icon: str = "❌"):
    """Muestra un mensaje de error."""
    st.error(f"{icon} **{title}**\n{message}")


def show_warning_message(title: str, message: str, icon: str = "⚠️"):
    """Muestra un mensaje de advertencia."""
    st.warning(f"{icon} **{title}**\n{message}")


def show_info_message(title: str, message: str, icon: str = "ℹ️"):
    """Muestra un mensaje de información."""
    st.info(f"{icon} **{title}**\n{message}")


def show_database_status(status: dict[str, Any]):
    """Muestra el estado de la conexión a BD en el sidebar."""
    st.sidebar.markdown("---")
    st.sidebar.subheader("📊 Estado del Sistema")

    if status.get("connected"):
        st.sidebar.success("✅ BD: Conectada")
    else:
        st.sidebar.error("❌ BD: Desconectada")

    if status.get("total_solicitudes"):
        st.sidebar.metric(
            "Solicitudes Registradas",
            status["total_solicitudes"],
            delta=f"+{status.get('solicitudes_hoy', 0)} hoy",
        )


def show_loading_spinner(message: str = "Cargando..."):
    """Muestra spinner de carga."""
    with st.spinner(message):
        yield


def render_solicitud_table(
    solicitudes: list[dict[str, Any]], on_select_callback=None
) -> str | None:
    """
    Renderiza tabla de solicitudes con botones de acción.

    Args:
        solicitudes: Lista de solicitudes
        on_select_callback: Callback cuando se selecciona una solicitud

    Returns:
        ID del lead seleccionado o None
    """
    if not solicitudes:
        st.info("No hay solicitudes registradas")
        return None

    # Mostrar tabla
    cols = st.columns([1, 2, 2, 1.5, 1, 1])

    with cols[0]:
        st.caption("**RUT**")
    with cols[1]:
        st.caption("**Nombre**")
    with cols[2]:
        st.caption("**Email**")
    with cols[3]:
        st.caption("**Fecha**")
    with cols[4]:
        st.caption("**Estado**")
    with cols[5]:
        st.caption("**Acción**")

    st.markdown("---")

    selected_id = None

    for solicitud in solicitudes:
        cols = st.columns([1, 2, 2, 1.5, 1, 1])

        with cols[0]:
            st.code(solicitud.get("rut", "N/A"), language=None)

        with cols[1]:
            st.text(solicitud.get("nombre_completo", "N/A")[:20])

        with cols[2]:
            st.text(solicitud.get("email", "N/A")[:20])

        with cols[3]:
            fecha = solicitud.get("created_at", "N/A")
            st.caption(str(fecha)[:10] if fecha else "N/A")

        with cols[4]:
            estado = solicitud.get("estado_lead", "pendiente")
            if estado == "pendiente":
                st.info(estado)
            elif estado == "aprobada":
                st.success(estado)
            else:
                st.warning(estado)

        with cols[5]:
            if st.button("📋", key=f"ver_{solicitud.get('id_lead', 'N/A')}", help="Ver detalle"):
                selected_id = solicitud.get("id_lead")
                if on_select_callback:
                    on_select_callback(selected_id)

        st.markdown("---")

    return selected_id


def show_solicitud_detalle(solicitud: dict[str, Any]):
    """Muestra detalle de una solicitud."""
    st.subheader("📋 Detalle de Solicitud")

    # Información personal
    st.markdown("### Datos Personales")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("RUT", value=solicitud.get("rut", ""), disabled=True)
        st.text_input("Email", value=solicitud.get("email", ""), disabled=True)
    with col2:
        st.text_input("Nombre", value=solicitud.get("nombre_completo", ""), disabled=True)
        st.text_input("Teléfono", value=solicitud.get("telefono", ""), disabled=True)

    # Solicitud
    st.markdown("### Datos de Solicitud")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("AFP", value=solicitud.get("afp", ""), disabled=True)
        st.text_input("Género", value=solicitud.get("genero", ""), disabled=True)
    with col2:
        st.text_input("Saldo AFP", value=f"${solicitud.get('saldo_afp', 0):,.0f}", disabled=True)
        st.text_input("Estado Civil", value=solicitud.get("estado_civil", ""), disabled=True)

    # Consentimientos
    st.markdown("### Consentimientos")
    col1, col2, col3 = st.columns(3)
    with col1:
        val = "✅ Aceptado" if solicitud.get("acepta_terminos") else "❌ Rechazado"
        st.text_input("Términos", value=val, disabled=True)
    with col2:
        val = "✅ Aceptado" if solicitud.get("acepta_politica_privacidad") else "❌ Rechazado"
        st.text_input("Privacidad", value=val, disabled=True)
    with col3:
        val = "✅ Sí" if solicitud.get("finalidad_contacto") else "❌ No"
        st.text_input("Contacto", value=val, disabled=True)

    # Metadata
    st.markdown("### Información del Registro")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input(
            "Fecha Creación",
            value=str(solicitud.get("created_at", ""))[:19],
            disabled=True,
        )
    with col2:
        st.text_input("Estado", value=solicitud.get("estado_lead", "pendiente"), disabled=True)

    # Comentarios
    if solicitud.get("comentarios"):
        st.markdown("### Comentarios")
        st.text_area("Notas", value=solicitud.get("comentarios", ""), disabled=True, height=100)


def show_pagination_info(page: int, page_size: int, total: int):
    """Muestra información de paginación."""
    total_pages = (total + page_size - 1) // page_size
    start = (page - 1) * page_size + 1
    end = min(page * page_size, total)

    st.caption(f"Mostrando {start}-{end} de {total} registros (Página {page}/{total_pages})")


def render_error_form_message(error: str):
    """Renderiza un error de formulario."""
    st.error(f"❌ Error al registrar solicitud:\n\n{error}")


def render_form_validation_error(field: str, error: str):
    """Renderiza un error de validación de campo específico."""
    st.error(f"❌ **{field}**: {error}")
