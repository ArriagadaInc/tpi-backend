"""Public Streamlit entrypoint for lead capture in TPI DEV."""

from __future__ import annotations

import streamlit as st

from app.presentation.public.landing import render_landing
from app.runtime import initialize_runtime, run_guarded
from app.services.solicitud_service import SolicitudService

st.set_page_config(page_title="Tu Pension Inteligente", page_icon="T", layout="wide")


@st.cache_resource
def get_service() -> SolicitudService:
    return SolicitudService()


def main() -> None:
    initialize_runtime("app.streamlit_app")
    render_landing(get_service())


if __name__ == "__main__":
    run_guarded(main, page_name="app.streamlit_app")
