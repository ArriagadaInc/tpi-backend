"""Configuración y fixtures para pytest."""

import os
import sys
from pathlib import Path

# Agregar el directorio raíz al path de Python
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configurar variables de entorno para tests
os.environ["APP_ENV"] = "testing"
os.environ["DATABASE_HOST"] = os.getenv("DATABASE_HOST", "localhost")
os.environ["DATABASE_PORT"] = os.getenv("DATABASE_PORT", "5432")
os.environ["DATABASE_NAME"] = os.getenv("DATABASE_NAME", "tpi_local")
os.environ["DATABASE_USER"] = os.getenv("DATABASE_USER", "tpi_app")
os.environ["DATABASE_PASSWORD"] = os.getenv("DATABASE_PASSWORD", "")
os.environ["DATABASE_SCHEMA"] = os.getenv("DATABASE_SCHEMA", "tpi")
