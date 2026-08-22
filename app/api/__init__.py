"""Public HTTP adapter for the static DEV frontend."""

from app.api.app import create_api_app

__all__ = ["create_api_app"]
