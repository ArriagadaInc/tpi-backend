"""
Página de Trazabilidad y Métricas.

Muestra:
- Estadísticas generales
- Gráficos de solicitudes por tiempo
- Distribución por AFP, género, estado civil
- Timeline de eventos
"""

from datetime import datetime

import pandas as pd
import streamlit as st

from app.components import show_error_message, show_header
from app.database import get_safe_error_message
from app.runtime import configure_logging, run_guarded
from app.services.solicitud_service import SolicitudService

st.set_page_config(
    page_title="Trazabilidad y Métricas",
    page_icon="📈",
    layout="wide",
)


@st.cache_resource
def get_service() -> SolicitudService:
    """Obtiene instancia del servicio."""
    return SolicitudService()


def main():
    """Función principal."""
    configure_logging()
    show_header()

    st.title("📈 Trazabilidad y Métricas")

    st.markdown("""
    Visualiza estadísticas y análisis de las solicitudes registradas.
    """)

    try:
        service = get_service()

        # Obtener datos
        result = service.get_solicitudes_lista(page=1, page_size=1000, masked=False)
        solicitudes = result.get("solicitudes", [])
        total = result.get("total", 0)

        # Si no hay datos
        if total == 0:
            st.info("No hay solicitudes para mostrar estadísticas")
            return

        # Convertir a DataFrame para análisis
        df = pd.DataFrame(solicitudes)

        # Sección 1: Estadísticas Generales
        st.markdown("## 📊 Estadísticas Generales")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total de Solicitudes", total)

        with col2:
            if "estado_lead" in df.columns:
                pendientes = len(df[df["estado_lead"] == "pendiente"])
                st.metric("Solicitudes Pendientes", pendientes)

        with col3:
            if "saldo_afp" in df.columns:
                saldo_promedio = df["saldo_afp"].mean()
                st.metric("Saldo Promedio AFP", f"${saldo_promedio:,.0f}")

        with col4:
            st.metric("Última Actualización", datetime.now().strftime("%H:%M:%S"))

        # Sección 2: Solicitudes por Día
        st.markdown("## 📅 Solicitudes por Fecha")

        if "created_at" in df.columns:
            # Convertir a datetime
            df["fecha"] = pd.to_datetime(df["created_at"]).dt.date

            # Agrupar por fecha
            by_date = df.groupby("fecha").size().reset_index(name="cantidad")

            col1, col2 = st.columns([3, 1])

            with col1:
                st.line_chart(by_date.set_index("fecha"))

            with col2:
                st.markdown("### Últimas Fechas")
                st.dataframe(
                    by_date.tail(5).rename(columns={"cantidad": "Registros"}),
                    use_container_width=True,
                    hide_index=True,
                )

        # Sección 3: Distribución por Catálogos
        st.markdown("## 🏦 Distribución por Catálogos")

        col1, col2, col3 = st.columns(3)

        with col1:
            if "afp" in df.columns and not df["afp"].isna().all():
                st.markdown("### Por AFP")
                afp_dist = df["afp"].value_counts()
                st.bar_chart(afp_dist)

        with col2:
            if "genero" in df.columns and not df["genero"].isna().all():
                st.markdown("### Por Género")
                genero_dist = df["genero"].value_counts()
                st.bar_chart(genero_dist)

        with col3:
            if "estado_civil" in df.columns and not df["estado_civil"].isna().all():
                st.markdown("### Por Estado Civil")
                estado_dist = df["estado_civil"].value_counts()
                st.bar_chart(estado_dist)

        # Sección 4: Estado de Solicitudes
        st.markdown("## 📋 Estado de Solicitudes")

        if "estado_lead" in df.columns:
            estado_dist = df["estado_lead"].value_counts()

            col1, col2 = st.columns([2, 1])

            with col1:
                st.bar_chart(estado_dist)

            with col2:
                st.markdown("### Resumen por Estado")
                for estado, count in estado_dist.items():
                    if estado == "pendiente":
                        st.warning(f"⏳ Pendiente: {count}")
                    elif estado == "aprobada":
                        st.success(f"✅ Aprobada: {count}")
                    else:
                        st.info(f"ℹ️ {estado.title()}: {count}")

        # Sección 5: Análisis de Saldo
        st.markdown("## 💰 Análisis de Saldo AFP")

        if "saldo_afp" in df.columns:
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Saldo Mínimo", f"${df['saldo_afp'].min():,.0f}")

            with col2:
                st.metric("Saldo Máximo", f"${df['saldo_afp'].max():,.0f}")

            with col3:
                st.metric("Saldo Promedio", f"${df['saldo_afp'].mean():,.0f}")

            with col4:
                st.metric("Saldo Mediano", f"${df['saldo_afp'].median():,.0f}")

            # Histograma de saldos
            st.markdown("### Distribución de Saldos")
            saldo_bins = df["saldo_afp"].astype(float).value_counts(bins=20).sort_index()
            st.bar_chart(saldo_bins)

        # Sección 6: Datos Brutos (para auditoría)
        st.markdown("---")
        st.markdown("## 📋 Datos Brutos")

        if st.checkbox("Mostrar tabla de solicitudes completa"):
            st.dataframe(df, use_container_width=True, height=400)

        # Exportar datos
        if st.button("📥 Descargar Datos (CSV)", use_container_width=True):
            csv = df.to_csv(index=False)
            st.download_button(
                label="Descargar CSV",
                data=csv,
                file_name=f"solicitudes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
            )

    except Exception as e:
        show_error_message(
            "Error al Cargar Métricas",
            get_safe_error_message(e),
        )


if __name__ == "__main__":
    run_guarded(main, page_name="app.pages.3_trazabilidad")
