"""CRM Lite backoffice board for lead operations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import streamlit as st

from app.auth import require_authenticated_user
from app.components import (
    format_datetime_short,
    render_crm_board,
    show_error_message,
    show_header,
    show_pagination_info,
    show_solicitud_detalle,
)
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
    if "crm_search" not in st.session_state:
        st.session_state.crm_search = ""
    if "crm_estado" not in st.session_state:
        st.session_state.crm_estado = "Todos"

    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([1.3, 1.1, 1.1, 1.1])
    with filter_col1:
        st.session_state.crm_search = st.text_input(
            "Buscar",
            value=st.session_state.crm_search,
            placeholder="RUT, nombre, email, teléfono o comentario",
            help="La búsqueda usa datos existentes del lead.",
        )
    with filter_col2:
        st.session_state.crm_estado = st.selectbox(
            "Estado",
            options=["Todos", "pendiente", "aprobada", "descartado"],
            index=["Todos", "pendiente", "aprobada", "descartado"].index(
                st.session_state.crm_estado
                if st.session_state.crm_estado in {"Todos", "pendiente", "aprobada", "descartado"}
                else "Todos"
            ),
        )
    with filter_col3:
        st.session_state.crm_sort_by = st.selectbox(
            "Ordenar por",
            options=["created_at", "nombre_completo", "rut", "saldo_afp", "estado_lead"],
            index=["created_at", "nombre_completo", "rut", "saldo_afp", "estado_lead"].index(
                st.session_state.crm_sort_by
                if st.session_state.crm_sort_by
                in {"created_at", "nombre_completo", "rut", "saldo_afp", "estado_lead"}
                else "created_at"
            ),
        )
    with filter_col4:
        st.session_state.crm_sort_direction = st.selectbox(
            "Dirección",
            options=["desc", "asc"],
            index=0 if st.session_state.crm_sort_direction != "asc" else 1,
        )

    page_size_col, refresh_col = st.columns([1, 1])
    with page_size_col:
        st.session_state.crm_page_size = st.selectbox(
            "Registros por página",
            options=[10, 20, 50, 100],
            index=[10, 20, 50, 100].index(st.session_state.crm_page_size),
        )
    with refresh_col:
        if st.button("Actualizar filtros", use_container_width=True):
            st.session_state.crm_page = 1
            _reset_selection()
            st.rerun()

    try:
        result = service.get_crm_bandeja(
            page=st.session_state.crm_page,
            page_size=st.session_state.crm_page_size,
            masked=True,
            search=st.session_state.crm_search.strip() or None,
            estado_lead=(
                None if st.session_state.crm_estado == "Todos" else st.session_state.crm_estado
            ),
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
                st.write("Nuevo")
                st.write("Contactado")
                st.write("Pendiente simulación")
                st.write("Simulación generada")
                st.write("En gestión")
                st.write("Cerrado")
                st.write("Descartado")

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

        st.markdown("---")
        st.subheader("Búsqueda por RUT")
        search_rut = st.text_input(
            "Ingresa RUT a buscar",
            placeholder="12345678-5",
            help="Formato: 12345678-5 o 12.345.678-5",
            key="crm_search_rut",
        )
        search_button = st.button("Buscar lead", use_container_width=True)
        if search_button and search_rut:
            solicitudes_rut = service.get_solicitudes_por_rut(search_rut, masked=True)
            if not solicitudes_rut:
                st.warning(f"No se encontraron leads para el RUT: {search_rut}")
            else:
                st.success(f"Se encontraron {len(solicitudes_rut)} lead(s)")
                render_crm_board(
                    solicitudes_rut,
                    on_select_callback=on_detail_click,
                    key_prefix="crm_busqueda",
                )

    except Exception as exc:
        show_error_message("Error al cargar la bandeja", get_safe_error_message(exc))


if __name__ == "__main__":
    run_guarded(main, page_name="app.pages.2_solicitudes_registradas")
