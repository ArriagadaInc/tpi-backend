"""ASGI entrypoint for the public API container."""

from app.api import create_api_app
from app.api.logging import configure_api_logging

configure_api_logging()
app = create_api_app()
