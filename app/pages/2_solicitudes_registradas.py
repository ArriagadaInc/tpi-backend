"""
Page to list and search registered requests.
"""

from __future__ import annotations

from uuid import UUID

import streamlit as st

from app.components import (
    render_solicitud_table,
    show_error_message,
    show_header,
    show_pagination_info,
    show_solicitud_detalle,
)
from app.database import get_safe_error_message
from app.runtime import configure_logging, run_guarded
from app.services.solicitud_service import SolicitudService

st.set_page_config(
    page_title="Solicitudes Registradas",
    page_icon="🔍",
    layout="wide",
)


@st.cache_resource
def get_service() -> SolicitudService:
    return SolicitudService()


def main() -> None:
    configure_logging()
    show_header()

    st.title("🔍 Solicitudes Registradas")
    st.markdown("""
        Busca y visualiza todas las solicitudes de simulacion registradas en el sistema.
        """)

    tab_listado, tab_busqueda = st.tabs(["📊 Listar Solicitudes", "🔎 Buscar por RUT"])

    with tab_listado:
        st.subheader("Todas las Solicitudes")
        page_size_col, _, _ = st.columns(3)
        with page_size_col:
            page_size = st.selectbox("Registros por pagina", options=[5, 10, 20, 50], index=1)

        try:
            service = get_service()
            if "current_page" not in st.session_state:
                st.session_state.current_page = 1

            result = service.get_solicitudes_lista(
                page=st.session_state.current_page,
                page_size=page_size,
                masked=True,
            )
            solicitudes = result.get("solicitudes", [])
            total = result.get("total", 0)
            total_pages = result.get("total_pages", 0)

            if total == 0:
                st.info("No hay solicitudes registradas aun.")
            else:
                show_pagination_info(st.session_state.current_page, page_size, total)

                def on_detail_click(id_lead: str) -> None:
                    st.session_state.selected_solicitud_id = id_lead
                    st.session_state.show_detail = True

                render_solicitud_table(
                    solicitudes,
                    on_select_callback=on_detail_click,
                    key_prefix="listado",
                )

                nav_col1, nav_col2, nav_col3, nav_col4, nav_col5 = st.columns(5)
                with nav_col1:
                    if st.session_state.current_page > 1 and st.button(
                        "⬅️ Anterior",
                        use_container_width=True,
                    ):
                        st.session_state.current_page -= 1
                        st.rerun()

                with nav_col2:
                    st.caption(f"Pagina {st.session_state.current_page} de {total_pages}")

                with nav_col5:
                    if st.session_state.current_page < total_pages and st.button(
                        "Siguiente ➡️",
                        use_container_width=True,
                    ):
                        st.session_state.current_page += 1
                        st.rerun()

        except Exception as exc:
            show_error_message(
                "Error al Cargar Solicitudes",
                get_safe_error_message(exc),
            )

    with tab_busqueda:
        st.subheader("Buscar Solicitudes por RUT")
        search_rut = st.text_input(
            "Ingresa RUT a buscar",
            placeholder="12345678-5",
            help="Formato: 12345678-5 o 12.345.678-5",
        )
        search_button = st.button("🔎 Buscar", use_container_width=True)

        if search_button and search_rut:
            try:
                service = get_service()
                solicitudes = service.get_solicitudes_por_rut(search_rut, masked=True)

                if not solicitudes:
                    st.warning(f"No se encontraron solicitudes para el RUT: {search_rut}")
                else:
                    st.success(f"Se encontraron {len(solicitudes)} solicitud(es)")

                    def on_detail_click(id_lead: str) -> None:
                        st.session_state.selected_solicitud_id = id_lead
                        st.session_state.show_detail = True

                    render_solicitud_table(
                        solicitudes,
                        on_select_callback=on_detail_click,
                        key_prefix="busqueda",
                    )

            except Exception as exc:
                show_error_message("Error en la Busqueda", get_safe_error_message(exc))

    st.markdown("---")

    if st.session_state.get("show_detail") and st.session_state.get("selected_solicitud_id"):
        try:
            service = get_service()
            id_lead = st.session_state.selected_solicitud_id
            solicitud = service.get_solicitud_detalle_masked(UUID(str(id_lead)))

            if solicitud:
                show_solicitud_detalle(solicitud)
                if st.button("✖️ Cerrar Detalle", use_container_width=True):
                    st.session_state.show_detail = False
                    st.rerun()
            else:
                st.error("No se encontro la solicitud seleccionada")

        except Exception as exc:
            show_error_message(
                "Error al Cargar Detalle",
                get_safe_error_message(exc),
            )


if __name__ == "__main__":
    run_guarded(main, page_name="app.pages.2_solicitudes_registradas")
