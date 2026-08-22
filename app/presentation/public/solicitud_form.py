"""Reusable public lead form that delegates all business work to SolicitudService."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import streamlit as st

from app.components import (
    render_form_validation_error,
    show_error_message,
    show_info_message,
    show_success_message,
)
from app.database import get_safe_error_message
from app.models.solicitud import (
    ConsentimientosData,
    PersonaData,
    RegistrarSolicitudRequest,
    SolicitudData,
)
from app.services.solicitud_service import SolicitudService


@dataclass(frozen=True, slots=True)
class PublicSolicitudFormData:
    """UI values required to construct the stable application request."""

    rut: str
    nombre_completo: str
    email: str
    telefono: str
    fecha_nacimiento: date
    genero_id: str
    estado_civil_id: str
    afp_id: str
    saldo_afp: int | float
    comentarios: str
    acepta_terminos: bool
    acepta_politica_privacidad: bool
    finalidad_contacto: bool


def load_catalogs(service: SolicitudService) -> dict[str, Any]:
    """Load approved catalog values through the service boundary."""
    try:
        afps = service.get_catalogo_afp()
        generos = service.get_catalogo_genero()
        estados_civiles = service.get_catalogo_estado_civil()
        return {
            "afps": {str(item["id"]): item["nombre"] for item in afps},
            "generos": {str(item["id"]): item["nombre"] for item in generos},
            "estados_civiles": {str(item["id"]): item["nombre"] for item in estados_civiles},
            "error": None,
        }
    except Exception as exc:
        return {
            "afps": {},
            "generos": {},
            "estados_civiles": {},
            "error": get_safe_error_message(exc),
        }


def build_solicitud_request(form_data: PublicSolicitudFormData) -> RegistrarSolicitudRequest:
    """Map bounded UI data to the existing validated application contract."""
    required_fields = {
        "RUT": form_data.rut,
        "Nombre": form_data.nombre_completo,
        "Email": form_data.email,
        "Telefono": form_data.telefono,
    }
    missing = [field for field, value in required_fields.items() if not value.strip()]
    if missing:
        raise ValueError("Campos obligatorios: " + ", ".join(missing))

    if not form_data.acepta_terminos or not form_data.acepta_politica_privacidad:
        raise ValueError("Debes aceptar los terminos y la politica de privacidad")
    if not form_data.finalidad_contacto:
        raise ValueError("Debes autorizar ser contactado")

    return RegistrarSolicitudRequest(
        persona=PersonaData(
            rut=form_data.rut,
            nombre_completo=form_data.nombre_completo,
            email=form_data.email,
            telefono=form_data.telefono,
            fecha_nacimiento=form_data.fecha_nacimiento,
        ),
        solicitud=SolicitudData(
            genero_id=UUID(form_data.genero_id),
            estado_civil_id=UUID(form_data.estado_civil_id),
            afp_id=UUID(form_data.afp_id),
            saldo_afp=Decimal(str(form_data.saldo_afp)),
            comentarios=form_data.comentarios or None,
        ),
        consentimientos=ConsentimientosData(
            acepta_terminos=form_data.acepta_terminos,
            acepta_politica_privacidad=form_data.acepta_politica_privacidad,
            finalidad_contacto=form_data.finalidad_contacto,
        ),
    )


def render_solicitud_form(service: SolicitudService, *, key_prefix: str = "public") -> None:
    """Render the public form without making auth or repository assumptions."""
    catalogs = load_catalogs(service)
    if catalogs["error"]:
        show_error_message("Formulario temporalmente no disponible", catalogs["error"])
        return
    if not all([catalogs["afps"], catalogs["generos"], catalogs["estados_civiles"]]):
        show_error_message("Formulario temporalmente no disponible", "Faltan catalogos requeridos.")
        return

    with st.form(f"{key_prefix}_solicitud_form"):
        st.subheader("Datos personales")
        col1, col2 = st.columns(2)
        with col1:
            rut = st.text_input("RUT *", placeholder="12345678-5")
            nombre = st.text_input("Nombre completo *", placeholder="Nombre Apellido")
            email = st.text_input("Email *", placeholder="nombre@ejemplo.cl")
        with col2:
            telefono = st.text_input("Telefono *", placeholder="+56912345678")
            fecha_nacimiento = st.date_input(
                "Fecha de nacimiento *",
                value=date(1990, 1, 1),
                min_value=date(1920, 1, 1),
                max_value=date.today(),
            )

        st.subheader("Datos de la solicitud")
        col1, col2 = st.columns(2)
        with col1:
            genero_id = st.selectbox(
                "Genero *",
                options=list(catalogs["generos"]),
                format_func=lambda value: catalogs["generos"][value],
            )
            estado_civil_id = st.selectbox(
                "Estado civil *",
                options=list(catalogs["estados_civiles"]),
                format_func=lambda value: catalogs["estados_civiles"][value],
            )
        with col2:
            afp_id = st.selectbox(
                "AFP *",
                options=list(catalogs["afps"]),
                format_func=lambda value: catalogs["afps"][value],
            )
            saldo_afp = st.number_input("Saldo AFP (CLP) *", min_value=0, value=100000, step=10000)

        comentarios = st.text_area("Comentarios (opcional)", max_chars=2000)
        st.subheader("Consentimientos")
        show_info_message(
            "Informacion importante",
            "Debes aceptar los terminos y la politica de privacidad para continuar.",
        )
        acepta_terminos = st.checkbox("Acepto los terminos y condiciones *")
        acepta_privacidad = st.checkbox("Acepto la politica de privacidad *")
        autoriza_contacto = st.checkbox("Autorizo ser contactado *")
        submitted = st.form_submit_button("Enviar solicitud", type="primary")

    if not submitted:
        return

    try:
        request = build_solicitud_request(
            PublicSolicitudFormData(
                rut=rut,
                nombre_completo=nombre,
                email=email,
                telefono=telefono,
                fecha_nacimiento=fecha_nacimiento,
                genero_id=genero_id,
                estado_civil_id=estado_civil_id,
                afp_id=afp_id,
                saldo_afp=saldo_afp,
                comentarios=comentarios,
                acepta_terminos=acepta_terminos,
                acepta_politica_privacidad=acepta_privacidad,
                finalidad_contacto=autoriza_contacto,
            )
        )
        response = service.registrar_solicitud(request)
    except ValueError as exc:
        render_form_validation_error("Validacion de datos", str(exc))
        return
    except Exception as exc:
        show_error_message("No fue posible registrar la solicitud", get_safe_error_message(exc))
        return

    show_success_message(
        "Solicitud registrada correctamente",
        f"Tu identificador de solicitud es: {response.id_lead}",
    )
