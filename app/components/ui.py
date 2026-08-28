"""Componentes reutilizables de UI para Streamlit."""

from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

import streamlit as st

from app.auth.guards import render_logout_control
from app.config import Settings, get_settings
from app.models.crm_states import crm_state_label, crm_state_tone, normalize_crm_state_for_display

_PUBLIC_SITE_BY_ENVIRONMENT = {
    "local": ("http", "tpi.localhost", 8080),
    "aws-dev": ("https", "backoffice.dev.tupensioninteligente.cl", None),
}


def get_public_site_url(settings: Settings) -> str | None:
    """Return the approved public DEV URL without credentials or query data."""
    expected = _PUBLIC_SITE_BY_ENVIRONMENT.get(settings.normalized_app_env)
    configured_url = settings.public_site_url
    if expected is None or not configured_url:
        return None

    try:
        parsed = urlsplit(configured_url)
        configured_port = parsed.port
    except ValueError:
        return None

    scheme, hostname, port = expected
    if (
        parsed.scheme != scheme
        or parsed.hostname != hostname
        or configured_port != port
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return None

    return configured_url.rstrip("/") + "/"


def render_public_site_link(settings: Settings) -> None:
    """Render public navigation without changing the authenticated session."""
    public_site_url = get_public_site_url(settings)
    if public_site_url is not None:
        st.sidebar.link_button("Volver al sitio", public_site_url, use_container_width=True)


def get_public_simulator_url(settings: Settings) -> str | None:
    """Return the approved simulator URL derived from the approved public host."""
    public_site_url = get_public_site_url(settings)
    if public_site_url is None:
        return None
    return public_site_url.rstrip("/") + "/simulador.html#simulador-interactivo"


def show_header():
    """Muestra el header de la aplicación."""
    settings = get_settings()
    render_logout_control()
    render_public_site_link(settings)
    st.markdown("---")
    col1, col2, col3 = st.columns([2, 3, 1])

    with col1:
        st.image("", width=100) if False else None  # Placeholder para logo

    with col2:
        st.title("💼 Tu Pensión Inteligente")
        st.caption("Back-office MVP - Simulador de pensiones")

    with col3:
        st.caption("v0.1.0 MVP")

    if settings.normalized_app_env == "aws-dev":
        st.warning("AMBIENTE DE DESARROLLO")
    else:
        st.caption(f"Ambiente: {settings.normalized_app_env}")

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


def format_currency_clp(value: Any) -> str:
    """Format a numeric value as Chilean pesos without introducing locale dependencies."""
    if value is None:
        return "N/A"
    try:
        amount = int(value)
    except (TypeError, ValueError):
        try:
            amount = int(float(value))
        except (TypeError, ValueError):
            return "N/A"
    return f"${amount:,}".replace(",", ".")


def format_datetime_short(value: Any) -> str:
    """Format a datetime-like value for dense CRM tables."""
    if value is None:
        return "N/A"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)[:16]


def lead_stage_label(estado_lead: Any) -> str:
    """Render a readable label for the current lead state without inventing persistence."""
    return crm_state_label(None if estado_lead is None else str(estado_lead))


def lead_stage_tone(estado_lead: Any) -> str:
    """Return a simple visual tone for the CRM board."""
    normalized = normalize_crm_state_for_display(None if estado_lead is None else str(estado_lead))
    if normalized is None:
        return "warning"
    return crm_state_tone(normalized)


def render_solicitud_table(
    solicitudes: list[dict[str, Any]],
    on_select_callback=None,
    key_prefix: str = "solicitudes",
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
        button_key = f"{key_prefix}_ver_{solicitud.get('id_lead', 'N/A')}"

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
            estado = lead_stage_label(solicitud.get("estado_lead"))
            render = getattr(st, lead_stage_tone(solicitud.get("estado_lead")), st.warning)
            render(estado)

        with cols[5]:
            if st.button("\U0001f4cb", key=button_key, help="Ver detalle"):
                selected_id = solicitud.get("id_lead")
                if on_select_callback:
                    on_select_callback(selected_id)

        st.markdown("---")

    return selected_id


def render_crm_board(
    solicitudes: list[dict[str, Any]],
    on_select_callback=None,
    key_prefix: str = "crm",
) -> str | None:
    """Render a dense CRM-like lead board."""
    if not solicitudes:
        st.info("No hay leads para mostrar con los filtros actuales.")
        return None

    cols = st.columns([1.1, 1.7, 1.2, 1.3, 1.2, 1.1, 1.1, 1.1, 0.8])
    headers = [
        "Fecha",
        "Nombre",
        "RUT",
        "Teléfono",
        "AFP",
        "Saldo",
        "Estado",
        "Simulación",
        "Acción",
    ]
    for col, header in zip(cols, headers, strict=True):
        with col:
            st.caption(f"**{header}**")
    st.markdown("---")

    selected_id = None
    for solicitud in solicitudes:
        row_cols = st.columns([1.1, 1.7, 1.2, 1.3, 1.2, 1.1, 1.1, 1.1, 0.8])
        lead_id = solicitud.get("id_lead", "N/A")
        button_key = f"{key_prefix}_open_{lead_id}"

        with row_cols[0]:
            st.caption(format_datetime_short(solicitud.get("created_at")))
        with row_cols[1]:
            st.markdown(f"**{solicitud.get('nombre_completo', 'N/A')}**")
        with row_cols[2]:
            st.code(str(solicitud.get("rut", "N/A")), language=None)
        with row_cols[3]:
            st.caption(str(solicitud.get("telefono", "N/A")))
        with row_cols[4]:
            st.caption(str(solicitud.get("afp", "N/A")))
        with row_cols[5]:
            st.caption(format_currency_clp(solicitud.get("saldo_afp")))
        with row_cols[6]:
            estado = lead_stage_label(solicitud.get("estado_lead"))
            tone = lead_stage_tone(solicitud.get("estado_lead"))
            render = getattr(st, tone, st.info)
            render(estado)
        with row_cols[7]:
            estado_canonical = normalize_crm_state_for_display(solicitud.get("estado_lead"))
            if estado_canonical == "nuevo":
                st.warning("Nuevo")
                st.caption("Acceso a simulación")
            else:
                st.success("Disponible")
                st.caption("Ver o continuar")
        with row_cols[8]:
            if st.button("Abrir", key=button_key, use_container_width=True):
                selected_id = lead_id
                if on_select_callback:
                    on_select_callback(selected_id)
        st.markdown("---")

    return selected_id


def render_lead_detail_panel(solicitud: dict[str, Any]) -> None:
    """Render a compact side-panel style detail for a selected lead."""
    settings = get_settings()
    st.subheader("Detalle del lead")

    top_cols = st.columns([2, 1])
    with top_cols[0]:
        st.markdown(f"### {solicitud.get('nombre_completo', 'N/A')}")
        st.caption(f"Lead ID: {solicitud.get('id_lead', 'N/A')}")
    with top_cols[1]:
        st.metric("Estado", lead_stage_label(solicitud.get("estado_lead")))

    st.markdown("#### Datos del lead")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("RUT", value=solicitud.get("rut", ""), disabled=True)
        st.text_input("Teléfono", value=solicitud.get("telefono", ""), disabled=True)
        st.text_input("AFP", value=solicitud.get("afp", ""), disabled=True)
    with col2:
        st.text_input("Email", value=solicitud.get("email", ""), disabled=True)
        st.text_input(
            "Saldo AFP", value=format_currency_clp(solicitud.get("saldo_afp")), disabled=True
        )
        st.text_input(
            "Fecha creación",
            value=format_datetime_short(solicitud.get("created_at")),
            disabled=True,
        )

    st.markdown("#### Simulación")
    estado = normalize_crm_state_for_display(solicitud.get("estado_lead"))
    if estado == "nuevo":
        st.info("El lead todavía está pendiente de simulación.")
    else:
        st.success("El lead ya tiene avance operativo registrado.")
    simulator_url = get_public_simulator_url(settings)
    if simulator_url is not None:
        st.link_button("Abrir simulador público", simulator_url, use_container_width=True)
    if solicitud.get("comentarios"):
        st.text_area(
            "Comentario operativo",
            value=solicitud.get("comentarios", ""),
            disabled=True,
            height=110,
        )

    st.markdown("#### Campos administrativos disponibles")
    admin_cols = st.columns(2)
    with admin_cols[0]:
        st.text_input("Género", value=solicitud.get("genero", ""), disabled=True)
        st.text_input("Estado civil", value=solicitud.get("estado_civil", ""), disabled=True)
    with admin_cols[1]:
        st.text_input(
            "Último estado", value=lead_stage_label(solicitud.get("estado_lead")), disabled=True
        )
        st.text_input(
            "Creado", value=format_datetime_short(solicitud.get("created_at")), disabled=True
        )
    st.caption(
        "La edición de estado, responsable y otros campos administrativos no está soportada "
        "por el esquema actual."
    )


def show_solicitud_detalle(solicitud: dict[str, Any]):
    """Muestra detalle de una solicitud."""
    render_lead_detail_panel(solicitud)


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
