"""
Script de verificación de conexión a PostgreSQL.

Ejecutar antes de iniciar la aplicación para verificar que:
1. PostgreSQL está accesible
2. El esquema TPI existe
3. Las tablas requeridas existen
4. Los catálogos tienen datos
"""

import sys
import logging

from app.config.settings import settings
from app.database import (
    initialize_pool,
    close_pool,
    check_database_connection,
    check_schema_exists,
    check_required_tables,
    check_catalogs,
)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Ejecutar verificación completa."""
    print("\n" + "=" * 70)
    print("Tu Pensión Inteligente - Verificación de Base de Datos")
    print("=" * 70)
    
    # Mostrar configuración (sin credenciales)
    print(f"\nConfiguración:")
    print(f"  Ambiente: {settings.app_env}")
    print(f"  Base de datos: {settings.database_name}")
    print(f"  Schema: {settings.database_schema}")
    print(f"  Host: {settings.database_host}:{settings.database_port}")
    print()
    
    # Inicializar pool
    try:
        initialize_pool()
    except Exception as e:
        logger.error(f"Error inicializando pool: {e}")
        print(f"\n❌ ERROR: No se pudo inicializar el pool de conexiones")
        print(f"   {e}")
        return False
    
    all_checks_passed = True
    
    # 1. Verificar conexión
    print("1. Verificando conexión a PostgreSQL...")
    health = check_database_connection()
    if health["connected"]:
        print(f"   ✅ {health['message']}")
    else:
        print(f"   ❌ {health['message']}")
        print(f"      Error: {health['error']}")
        all_checks_passed = False
    
    if not health["connected"]:
        close_pool()
        return False
    
    # 2. Verificar esquema
    print("\n2. Verificando esquema TPI...")
    schema_check = check_schema_exists()
    if schema_check["exists"]:
        print(f"   ✅ {schema_check['message']}")
    else:
        print(f"   ❌ Esquema no encontrado")
        all_checks_passed = False
    
    if not schema_check["exists"]:
        close_pool()
        return False
    
    # 3. Verificar tablas requeridas
    print("\n3. Verificando tablas requeridas...")
    tables_check = check_required_tables()
    print(f"   Encontradas: {len(tables_check['found'])}/{len(tables_check['required'])}")
    for table in tables_check["found"]:
        print(f"     ✅ {table}")
    for table in tables_check["missing"]:
        print(f"     ❌ {table}")
        all_checks_passed = False
    
    # 4. Verificar catálogos
    print("\n4. Verificando catálogos...")
    catalogs_check = check_catalogs()
    print(f"   AFP: {catalogs_check['afp_count']} opciones activas", end="")
    print(f" ✅" if catalogs_check['afp_count'] > 0 else " ❌")
    print(f"   Género: {catalogs_check['genero_count']} opciones activas", end="")
    print(f" ✅" if catalogs_check['genero_count'] > 0 else " ❌")
    print(f"   Estado Civil: {catalogs_check['estado_civil_count']} opciones activas", end="")
    print(f" ✅" if catalogs_check['estado_civil_count'] > 0 else " ❌")
    
    if not catalogs_check["all_ready"]:
        all_checks_passed = False
    
    # Resumen
    print("\n" + "=" * 70)
    if all_checks_passed:
        print("✅ TODAS LAS VERIFICACIONES PASARON CORRECTAMENTE")
        print("   La aplicación está lista para iniciar.")
    else:
        print("❌ ALGUNAS VERIFICACIONES FALLARON")
        print("   Revisa los errores arriba antes de continuar.")
    print("=" * 70 + "\n")
    
    close_pool()
    return all_checks_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
