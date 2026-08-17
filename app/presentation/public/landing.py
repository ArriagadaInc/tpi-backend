"""Public landing page and lead-capture composition."""

from __future__ import annotations

import streamlit as st

from app.presentation.public.solicitud_form import render_solicitud_form
from app.services.solicitud_service import SolicitudService


def hide_private_navigation() -> None:
    """Hide automatic page discovery on the public host.

    Private page scripts retain their own guards; this is presentation only.
    """
    st.markdown(
        "<style>[data-testid='stSidebarNav'] { display: none; }</style>",
        unsafe_allow_html=True,
    )


def render_landing(service: SolicitudService) -> None:
    """Render the unauthenticated public lead journey."""
    hide_private_navigation()
    st.title("Tu Pension Inteligente")
    st.caption("Ambiente de Desarrollo")
    st.info("Solicita una simulacion o deja tus datos para que podamos contactarte.")
    st.markdown("## Solicita tu simulacion")
    render_solicitud_form(service)
