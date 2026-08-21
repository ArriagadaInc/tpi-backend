"""CRM Lite backoffice board for lead operations."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

import streamlit as st

from app.auth import require_authenticated_user
from app.components import (
    format_datetime_short,
    get_public_simulator_url,
    render_crm_board,
    show_error_message,
    show_header,
    show_pagination_info,
    show_solicitud_detalle,
)
from app.config import get_settings
from app.database import get_safe_error_message
from app.runtime import configure_logging, run_guarded
from app.services.solicitud_service import SolicitudService

st.set_page_config(
    page_title="Bandeja de Leads",
    page_icon="📋",
    layout="wide",
)


@st.cache_resource
def get_service() -> SolicitudService:
    return SolicitudService()


def _reset_selection() -> None:
    st.session_state.pop("selected_solicitud_id", None)
    st.session_state.pop("show_detail", None)


def _resolve_afp_id(selected_name: str, afp_catalog: list[dict[str, object]]) -> UUID | None:
    if selected_name == "Todas":
        return None
    for afp in afp_catalog:
        if afp.get("nombre") == selected_name:
            return UUID(str(afp["id"]))
    return None


def _parse_optional_date(raw_value: str) -> date | None:
    value = raw_value.strip()
    if not value:
        return None
    return date.fromisoformat(value)


def _reset_filters() -> None:
    st.session_state.crm_search = ""
    st.session_state.crm_estado = "Todos"
    st.session_state.crm_afp = "Todas"
    st.session_state.crm_date_from = ""
    st.session_state.crm_date_to = ""
    st.session_state.crm_sort_label = "Más recientes primero"
    st.session_state.crm_sort_direction = "desc"
    st.session_state.crm_sort_by = "created_at"
    st.session_state.crm_page = 1
    _reset_selection()


def main() -> None:
    configure_logging()
    require_authenticated_user()
    show_header()

    cleanup_success_message = st.session_state.pop("test_lead_cleanup_success", None)
    if cleanup_success_message:
        st.success(cleanup_success_message)

    st.title("Bandeja de Leads")
    st.markdown(
        "Vista tipo CRM para operar leads con densidad alta de información, "
        "búsqueda rápida y acceso directo al detalle."
    )

    service = get_service()
    if "crm_page" not in st.session_state:
        st.session_state.crm_page = 1
    if "crm_page_size" not in st.session_state:
        st.session_state.crm_page_size = 20
    if "crm_sort_by" not in st.session_state:
        st.session_state.crm_sort_by = "created_at"
    if "crm_sort_direction" not in st.session_state:
        st.session_state.crm_sort_direction = "desc"
    if "crm_sort_label" not in st.session_state:
        st.session_state.crm_sort_label = "Más recientes primero"
    if "crm_search" not in st.session_state:
        st.session_state.crm_search = ""
    if "crm_estado" not in st.session_state:
        st.session_state.crm_estado = "Todos"
    if "crm_afp" not in st.session_state:
        st.session_state.crm_afp = "Todas"
    if "crm_date_from" not in st.session_state:
        st.session_state.crm_date_from = ""
    if "crm_date_to" not in st.session_state:
        st.session_state.crm_date_to = ""

    afp_catalog = service.get_catalogo_afp()
    afp_options = ["Todas"] + [afp["nombre"] for afp in afp_catalog]
    estado_options = ["Todos"] + service.get_crm_estado_lead_options()

    st.subheader("Leads")
    st.text_input(
        "Buscar nombre o RUT",
        value=st.session_state.crm_search,
        placeholder="Nombre o RUT",
        help="Filtra por nombre completo o por RUT sin cargar todo en memoria.",
        key="crm_search",
    )

    filter_col1, filter_col2, filter_col3, filter_col4, filter_col5 = st.columns(
        [1.0, 1.0, 0.9, 0.9, 1.0]
    )
    with filter_col1:
        st.selectbox("AFP", options=afp_options, key="crm_afp")
    with filter_col2:
        st.selectbox("Estado", options=estado_options, key="crm_estado")
    with filter_col3:
        st.text_input(
            "Desde",
            value=st.session_state.crm_date_from,
            placeholder="YYYY-MM-DD",
            help="Fecha inicial en formato ISO, por ejemplo 2026-08-01.",
            key="crm_date_from",
        )
    with filter_col4:
        st.text_input(
            "Hasta",
            value=st.session_state.crm_date_to,
            placeholder="YYYY-MM-DD",
            help="Fecha final en formato ISO, por ejemplo 2026-08-21.",
            key="crm_date_to",
        )
    with filter_col5:
        st.selectbox(
            "Ordenar",
            options=["Más recientes primero", "Más antiguas primero"],
            key="crm_sort_label",
        )

    action_col1, action_col2, action_col3 = st.columns([1, 1, 1])
    with action_col1:
        st.selectbox(
            "Registros por página",
            options=[10, 20, 50, 100],
            key="crm_page_size",
        )
    with action_col2:
        if st.button("Actualizar filtros", use_container_width=True):
            st.session_state.crm_page = 1
            _reset_selection()
            st.rerun()
    with action_col3:
        if st.button("Limpiar filtros", use_container_width=True):
            _reset_filters()
            st.rerun()

    st.session_state.crm_sort_direction = (
        "asc" if st.session_state.get("crm_sort_label") == "Más antiguas primero" else "desc"
    )
    st.session_state.crm_sort_by = "created_at"
    crm_date_from_raw = st.session_state.crm_date_from.strip()
    crm_date_to_raw = st.session_state.crm_date_to.strip()

    try:
        normalized_date_from = _parse_optional_date(crm_date_from_raw)
        normalized_date_to = _parse_optional_date(crm_date_to_raw)
    except ValueError:
        show_error_message(
            "Error de filtros",
            "Las fechas deben usar el formato YYYY-MM-DD.",
        )
        st.stop()

    try:
        result = service.get_crm_bandeja(
            page=st.session_state.crm_page,
            page_size=st.session_state.crm_page_size,
            masked=True,
            search=st.session_state.crm_search.strip() or None,
            estado_lead=(
                None if st.session_state.crm_estado == "Todos" else st.session_state.crm_estado
            ),
            afp_id=_resolve_afp_id(st.session_state.crm_afp, afp_catalog),
            date_from=normalized_date_from,
            date_to=normalized_date_to,
            sort_by=st.session_state.crm_sort_by,
            sort_direction=st.session_state.crm_sort_direction,
        )
        solicitudes = result.get("solicitudes", [])
        total = result.get("total", 0)
        total_pages = result.get("total_pages", 0)

        metric_cols = st.columns(4)
        with metric_cols[0]:
            st.metric("Leads visibles", total)
        with metric_cols[1]:
            st.metric("Página actual", f"{result.get('page', 1)} / {total_pages or 1}")
        with metric_cols[2]:
            st.metric(
                "Orden", f"{st.session_state.crm_sort_by} · {st.session_state.crm_sort_direction}"
            )
        with metric_cols[3]:
            st.metric("Última carga", format_datetime_short(datetime.now()))

        if total == 0:
            st.info("No hay leads para mostrar con los filtros actuales.")
        else:
            show_pagination_info(result.get("page", 1), result.get("page_size", 20), total)
            board_col, detail_col = st.columns([2.2, 1.2], gap="large")

            def on_detail_click(id_lead: str) -> None:
                st.session_state.selected_solicitud_id = id_lead
                st.session_state.show_detail = True

            with board_col:
                render_crm_board(
                    solicitudes,
                    on_select_callback=on_detail_click,
                    key_prefix="crm_bandeja",
                )

                nav_col1, nav_col2, nav_col3 = st.columns([1, 1, 1])
                with nav_col1:
                    if st.session_state.crm_page > 1 and st.button(
                        "⬅️ Anterior", use_container_width=True
                    ):
                        st.session_state.crm_page -= 1
                        st.rerun()
                with nav_col2:
                    st.caption(f"Página {st.session_state.crm_page} de {total_pages or 1}")
                with nav_col3:
                    if st.session_state.crm_page < total_pages and st.button(
                        "Siguiente ➡️",
                        use_container_width=True,
                    ):
                        st.session_state.crm_page += 1
                        st.rerun()

            with detail_col:
                st.markdown("### Flujo operativo")
                st.caption(
                    "Nuevo → Contactado → Pendiente simulación → Simulación generada → En gestión → Cerrado"
                )
                st.caption("Salida alternativa: Descartado")

                if st.session_state.get("show_detail") and st.session_state.get(
                    "selected_solicitud_id"
                ):
                    solicitud = service.get_solicitud_detalle_masked(
                        UUID(str(st.session_state.selected_solicitud_id))
                    )
                    if solicitud:
                        show_solicitud_detalle(solicitud)
                        if service.is_test_lead_cleanup_enabled():
                            st.markdown("---")
                            st.subheader("Eliminar lead de prueba")
                            st.warning("Esta acción solo elimina datos ficticios del ambiente DEV.")
                            confirmed_test_data = st.checkbox(
                                "Confirmo que este es un dato de prueba",
                                key=f"delete_test_lead_confirm_{st.session_state.selected_solicitud_id}",
                            )
                            confirmation_text = st.text_input(
                                "Escribe ELIMINAR para confirmar",
                                key=f"delete_test_lead_text_{st.session_state.selected_solicitud_id}",
                            )
                            if st.button(
                                "ELIMINAR LEAD DE PRUEBA",
                                key=f"delete_test_lead_button_{st.session_state.selected_solicitud_id}",
                                type="primary",
                                disabled=not (
                                    confirmed_test_data and confirmation_text == "ELIMINAR"
                                ),
                            ):
                                cleanup_result = service.delete_test_lead(
                                    st.session_state.selected_solicitud_id
                                )
                                if cleanup_result.deleted:
                                    st.session_state.test_lead_cleanup_success = (
                                        cleanup_result.message
                                    )
                                    _reset_selection()
                                    st.rerun()
                                else:
                                    st.error(cleanup_result.message)
                        if st.button("✖️ Cerrar detalle", use_container_width=True):
                            _reset_selection()
                            st.rerun()
                    else:
                        st.error("No se encontró el lead seleccionado.")
                else:
                    st.info("Selecciona un lead para ver su detalle.")
                    simulator_url = get_public_simulator_url(get_settings())
                    if simulator_url:
                        st.link_button(
                            "Abrir simulador público", simulator_url, use_container_width=True
                        )

    except Exception as exc:
        show_error_message("Error al cargar la bandeja", get_safe_error_message(exc))


if __name__ == "__main__":
    run_guarded(main, page_name="app.pages.2_solicitudes_registradas")
