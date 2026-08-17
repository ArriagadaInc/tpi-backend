"""Authenticated access to the shared lead form for backoffice operators."""

from __future__ import annotations

import streamlit as st

from app.auth import require_authenticated_user
from app.components import show_header
from app.presentation.public.solicitud_form import render_solicitud_form
from app.runtime import configure_logging, run_guarded
from app.services.solicitud_service import SolicitudService

st.set_page_config(page_title="Registrar solicitud", page_icon="R", layout="wide")


@st.cache_resource
def get_service() -> SolicitudService:
    return SolicitudService()


def main() -> None:
    configure_logging()
    require_authenticated_user()
    show_header()
    st.title("Registrar solicitud")
    st.caption(
        "Esta vista privada reutiliza el mismo contrato de aplicacion del formulario publico."
    )
    render_solicitud_form(get_service(), key_prefix="backoffice")


if __name__ == "__main__":
    run_guarded(main, page_name="app.pages.1_registrar_solicitud")
