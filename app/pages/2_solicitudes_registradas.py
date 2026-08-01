"""
Página para consultar y visualizar solicitudes registradas.

Permite:
- Buscar por RUT
- Listar solicitudes con paginación
- Ver detalles de una solicitud
- Filtros opcionales
"""

from uuid import UUID

import streamlit as st

from app.components import (
    render_solicitud_table,
    show_error_message,
    show_header,
    show_pagination_info,
    show_solicitud_detalle,
)
from app.services.solicitud_service import SolicitudService

st.set_page_config(
    page_title="Solicitudes Registradas",
    page_icon="🔍",
    layout="wide",
)


@st.cache_resource
def get_service() -> SolicitudService:
    """Obtiene instancia del servicio."""
    return SolicitudService()


def main():
    """Función principal."""
    show_header()

    st.title("🔍 Solicitudes Registradas")

    st.markdown("""
    Busca y visualiza todas las solicitudes de simulación registradas en el sistema.
    """)

    # Tabs para diferentes vistas
    tab1, tab2 = st.tabs(["📊 Listar Solicitudes", "🔎 Buscar por RUT"])

    # TAB 1: Listar Solicitudes
    with tab1:
        st.subheader("Todas las Solicitudes")

        # Controles de paginación
        col1, col2, col3 = st.columns(3)

        with col1:
            page_size = st.selectbox(
                "Registros por página",
                options=[5, 10, 20, 50],
                index=1,
            )

        with col2:
            # Placeholder para filtro de estado (futuro)
            pass

        with col3:
            # Placeholder para filtro de rango de fechas (futuro)
            pass

        # Obtener solicitudes
        try:
            service = get_service()

            # Inicializar sesión si no existe
            if "current_page" not in st.session_state:
                st.session_state.current_page = 1

            # Obtener datos
            result = service.get_solicitudes_lista(
                page=st.session_state.current_page, page_size=page_size, masked=True
            )

            solicitudes = result.get("solicitudes", [])
            total = result.get("total", 0)
            total_pages = result.get("total_pages", 0)

            if total == 0:
                st.info("No hay solicitudes registradas aún.")
            else:
                # Mostrar información de paginación
                show_pagination_info(st.session_state.current_page, page_size, total)

                # Renderizar tabla
                def on_detail_click(id_lead):
                    st.session_state.selected_solicitud_id = id_lead
                    st.session_state.show_detail = True

                render_solicitud_table(solicitudes, on_select_callback=on_detail_click)

                # Controles de paginación
                col1, col2, col3, col4, col5 = st.columns(5)

                with col1:
                    if st.session_state.current_page > 1:
                        if st.button("⬅️ Anterior", use_container_width=True):
                            st.session_state.current_page -= 1
                            st.rerun()

                with col2:
                    st.caption(f"Página {st.session_state.current_page} de {total_pages}")

                with col3:
                    pass

                with col4:
                    pass

                with col5:
                    if st.session_state.current_page < total_pages:
                        if st.button("Siguiente ➡️", use_container_width=True):
                            st.session_state.current_page += 1
                            st.rerun()

        except Exception as e:
            show_error_message(
                "Error al Cargar Solicitudes",
                f"No se pudieron cargar las solicitudes: {str(e)}",
            )

    # TAB 2: Buscar por RUT
    with tab2:
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

                    # Mostrar tabla de resultados
                    def on_detail_click(id_lead):
                        st.session_state.selected_solicitud_id = id_lead
                        st.session_state.show_detail = True

                    render_solicitud_table(solicitudes, on_select_callback=on_detail_click)

            except Exception as e:
                show_error_message("Error en la Búsqueda", f"Ocurrió un error: {str(e)}")

    # Mostrar detalle si está seleccionado
    st.markdown("---")

    if st.session_state.get("show_detail") and st.session_state.get("selected_solicitud_id"):
        try:
            service = get_service()
            id_lead = st.session_state.selected_solicitud_id

            # Obtener detalle sin enmascaramiento (para admin)
            # En producción habría que verificar permisos
            solicitud = service.get_solicitud_detalle_masked(UUID(str(id_lead)))

            if solicitud:
                show_solicitud_detalle(solicitud)

                # Botón para cerrar detalle
                if st.button("✖️ Cerrar Detalle", use_container_width=True):
                    st.session_state.show_detail = False
                    st.rerun()
            else:
                st.error("No se encontró la solicitud seleccionada")

        except Exception as e:
            show_error_message("Error al Cargar Detalle", f"No se pudo cargar el detalle: {str(e)}")


if __name__ == "__main__":
    main()
