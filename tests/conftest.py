"""Configuración y fixtures para pytest."""

import os
import sys
from pathlib import Path

# Agregar el directorio raíz al path de Python
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Ambiente de pruebas. No forzar credenciales de BD aquí: Settings ya las
# carga desde .env; sobreescribirlas con valores por defecto incorrectos
# (p.ej. usuario "tpi_app" inexistente) rompe la conexión real en tests.
os.environ.setdefault("APP_ENV", "testing")
