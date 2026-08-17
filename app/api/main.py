"""ASGI entrypoint for the public API container."""

from app.api import create_api_app

app = create_api_app()
