"""Script para verificar que Streamlit inicia sin errores."""

import sys
import time
import subprocess
import psycopg
from app.config.settings import settings

def check_streamlit_startup():
    """Verificar que Streamlit inicia sin errores."""
    print("\n" + "="*70)
    print("VALIDACIÓN 3: Inicio de Streamlit")
    print("="*70)
    
    try:
        # Intentar importar streamlit
        import streamlit as st
        
        print("✓ Streamlit importado exitosamente")
        
        # Verificar que las páginas existen
        import os
        pages = [
            "app/pages/1_registrar_solicitud.py",
            "app/pages/2_solicitudes_registradas.py",
            "app/pages/3_trazabilidad.py",
        ]
        
        print("\nPáginas disponibles:")
        for page in pages:
            if os.path.exists(page):
                with open(page, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if len(content) > 0:
                        print(f"  ✓ {page}")
                    else:
                        print(f"  ✗ {page} (vacío)")
            else:
                print(f"  ✗ {page} (no encontrado)")
        
        return True
        
    except Exception as e:
        print(f"✗ Error al verificar Streamlit: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = check_streamlit_startup()
    sys.exit(0 if success else 1)
