"""
Página para registrar una nueva solicitud de simulación.

Formulario completo con:
- Datos personales
- Datos de solicitud
- Consentimientos
- Validación automática
"""

import streamlit as st
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.services.solicitud_service import SolicitudService
from app.models.solicitud import (
    PersonaData,
    SolicitudData,
    ConsentimientosData,
    RegistrarSolicitudRequest,
)
from app.components import (
    show_header,
    show_success_message,
    show_error_message,
    show_info_message,
    render_form_validation_error,
)


st.set_page_config(
    page_title="Registrar Solicitud",
    page_icon="📝",
    layout="wide",
)


@st.cache_resource
def get_service() -> SolicitudService:
    """Obtiene instancia del servicio."""
    return SolicitudService()


def load_catalogs():
    """Carga los catálogos de BD."""
    service = get_service()
    
    try:
        afps = service.get_catalogo_afp()
        generos = service.get_catalogo_genero()
        estados_civiles = service.get_catalogo_estado_civil()
        
        return {
            "afps": {str(a["id"]): a["nombre"] for a in afps},
            "generos": {str(g["id"]): g["nombre"] for g in generos},
            "estados_civiles": {str(ec["id"]): ec["nombre"] for ec in estados_civiles},
            "error": None,
        }
    except Exception as e:
        return {
            "afps": {},
            "generos": {},
            "estados_civiles": {},
            "error": str(e),
        }


def main():
    """Función principal."""
    show_header()
    
    st.title("📝 Registrar Nueva Solicitud")
    
    st.markdown("""
    Complete el formulario a continuación para registrar una nueva solicitud de simulación.
    Todos los campos marcados con * son obligatorios.
    """)
    
    # Cargar catálogos
    catalogs = load_catalogs()
    
    if catalogs["error"]:
        show_error_message(
            "Error al Cargar Catálogos",
            f"No se pudieron cargar los datos necesarios: {catalogs['error']}"
        )
        st.stop()
    
    if not all([catalogs["afps"], catalogs["generos"], catalogs["estados_civiles"]]):
        show_error_message(
            "Datos Incompletos",
            "Faltan catálogos de AFP, género o estado civil."
        )
        st.stop()
    
    # Formulario
    with st.form("solicitud_form"):
        # Sección 1: Datos Personales
        st.subheader("👤 Datos Personales")
        
        col1, col2 = st.columns(2)
        
        with col1:
            rut = st.text_input(
                "RUT *",
                placeholder="12345678-5",
                help="Formato: 12345678-5 o 12.345.678-5"
            )
            
            nombre = st.text_input(
                "Nombre Completo *",
                placeholder="Juan Carlos Pérez García",
                help="Sin números, con espacios normalizados"
            )
            
            email = st.text_input(
                "Email *",
                placeholder="juan@example.com",
                help="Email válido de máximo 254 caracteres"
            )
        
        with col2:
            telefono = st.text_input(
                "Teléfono *",
                placeholder="+56912345678",
                help="Formato chileno celular: +56912345678 o 0912345678"
            )
            
            fecha_nacimiento = st.date_input(
                "Fecha de Nacimiento *",
                value=date(1990, 1, 1),
                min_value=date(1920, 1, 1),
                max_value=date.today(),
                help="Selecciona una fecha válida (no futura)"
            )
        
        # Sección 2: Datos de Solicitud
        st.subheader("📋 Datos de Solicitud")
        
        col1, col2 = st.columns(2)
        
        with col1:
            genero_id = st.selectbox(
                "Género *",
                options=list(catalogs["generos"].keys()),
                format_func=lambda x: catalogs["generos"].get(x, ""),
                help="Selecciona tu género"
            )
            
            estado_civil_id = st.selectbox(
                "Estado Civil *",
                options=list(catalogs["estados_civiles"].keys()),
                format_func=lambda x: catalogs["estados_civiles"].get(x, ""),
                help="Selecciona tu estado civil"
            )
        
        with col2:
            afp_id = st.selectbox(
                "AFP *",
                options=list(catalogs["afps"].keys()),
                format_func=lambda x: catalogs["afps"].get(x, ""),
                help="Selecciona tu AFP"
            )
            
            saldo_afp = st.number_input(
                "Saldo AFP (CLP) *",
                min_value=0,
                value=100000,
                step=10000,
                help="Saldo en pesos chilenos (sin decimales)"
            )
        
        # Comentarios opcionales
        comentarios = st.text_area(
            "Comentarios (Opcional)",
            placeholder="Agregar notas o comentarios adicionales...",
            help="Campo opcional para notas",
            height=100
        )
        
        # Sección 3: Consentimientos
        st.subheader("✅ Consentimientos")
        
        show_info_message(
            "Información Importante",
            "Debes aceptar los términos y la política de privacidad para continuar."
        )
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            acepta_terminos = st.checkbox(
                "Acepto los Términos y Condiciones *",
                value=False,
                help="Debe ser aceptado obligatoriamente"
            )
        
        with col2:
            acepta_privacidad = st.checkbox(
                "Acepto la Política de Privacidad *",
                value=False,
                help="Debe ser aceptado obligatoriamente"
            )
        
        with col3:
            autoriza_contacto = st.checkbox(
                "Autorizo ser contactado *",
                value=False,
                help="Permitir contacto para seguimiento"
            )
        
        # Botón de envío
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            submit_button = st.form_submit_button(
                "✅ Registrar Solicitud",
                use_container_width=True,
                type="primary"
            )
        
        with col2:
            st.form_submit_button(
                "🔄 Limpiar Formulario",
                use_container_width=True,
            )
    
    # Procesar envío
    if submit_button:
        # Validaciones básicas
        errors = []
        
        if not rut:
            errors.append("RUT es obligatorio")
        
        if not nombre:
            errors.append("Nombre es obligatorio")
        
        if not email:
            errors.append("Email es obligatorio")
        
        if not telefono:
            errors.append("Teléfono es obligatorio")
        
        if not acepta_terminos:
            errors.append("Debes aceptar los Términos y Condiciones")
        
        if not acepta_privacidad:
            errors.append("Debes aceptar la Política de Privacidad")
        
        if not autoriza_contacto:
            errors.append("Debes autorizar ser contactado")
        
        if errors:
            for error in errors:
                render_form_validation_error("Validación", error)
            st.stop()
        
        # Registrar solicitud
        with st.spinner("Registrando solicitud..."):
            try:
                service = get_service()
                
                # Crear request con datos validados
                request = RegistrarSolicitudRequest(
                    persona=PersonaData(
                        rut=rut,
                        nombre_completo=nombre,
                        email=email,
                        telefono=telefono,
                        fecha_nacimiento=fecha_nacimiento,
                    ),
                    solicitud=SolicitudData(
                        genero_id=UUID(genero_id),
                        estado_civil_id=UUID(estado_civil_id),
                        afp_id=UUID(afp_id),
                        saldo_afp=Decimal(str(saldo_afp)),
                        comentarios=comentarios if comentarios else None,
                    ),
                    consentimientos=ConsentimientosData(
                        acepta_terminos=acepta_terminos,
                        acepta_politica_privacidad=acepta_privacidad,
                        finalidad_contacto=autoriza_contacto,
                    ),
                )
                
                # Registrar en servicio
                response = service.registrar_solicitud(request)
                
                # Mostrar éxito
                show_success_message(
                    "Solicitud Registrada Exitosamente",
                    f"""
                    ✅ Tu solicitud ha sido registrada correctamente.
                    
                    **ID Solicitud**: {response.id_lead}
                    **Nombre**: {response.nombre_completo}
                    **Estado**: {response.estado_lead}
                    
                    {response.mensaje}
                    """
                )
                
                st.markdown("---")
                st.info("📌 Puedes consultar el estado de tu solicitud en la sección 'Solicitudes Registradas'")
                
                # Limpiar session state
                st.session_state.clear()
            
            except ValueError as e:
                render_form_validation_error("Validación de Datos", str(e))
                st.markdown("""
                **Causas comunes**:
                - RUT con dígito verificador incorrecto
                - Email o teléfono en formato inválido
                - Fecha de nacimiento futura o en rango inválido
                """)
            
            except Exception as e:
                show_error_message(
                    "Error al Registrar Solicitud",
                    f"Ocurrió un error inesperado: {str(e)}"
                )


if __name__ == "__main__":
    main()
