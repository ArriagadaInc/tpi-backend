"""CLI verification for the configured PostgreSQL connection."""

from __future__ import annotations

import logging
import sys

from app.config import get_settings
from app.database import close_pool
from app.database.errors import DatabaseAppError, classify_database_exception
from app.database.healthcheck import (
    check_catalogs,
    check_database_connection,
    check_required_tables,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> bool:
    print("\n" + "=" * 70)
    print("Tu Pension Inteligente - Verificacion de Base de Datos")
    print("=" * 70)

    try:
        settings = get_settings()
        config = settings.database_config
    except Exception as exc:
        error = classify_database_exception(exc, operation="verify_database_connection")
        print("\n[FAIL] No se pudo resolver la configuracion de base de datos")
        print(f"   {error.user_message}")
        print(f"   Detalle tecnico: {error.technical_message}")
        return False

    print("\nConfiguracion efectiva:")
    print(f"  Ambiente: {config.app_env}")
    print(f"  Origen: {config.source}")
    print(f"  Objetivo: {config.host}:{config.port}/{config.database}")
    print(f"  Usuario esperado: {config.user}")
    print(f"  Esquema: {config.schema}")
    print(f"  SSL: {config.sslmode}")
    print(f"  Pool: {config.pool_min_size}-{config.pool_max_size}")

    all_checks_passed = True

    try:
        print("\n1. Verificando conectividad y acceso...")
        health = check_database_connection()
        if health["connected"]:
            print(f"   [OK] {health['message']}")
            print(f"   Usuario efectivo: {health['effective_user']}")
            print(f"   Esquema accesible: {health['schema_accessible']}")
            print(f"   tpi.leads accesible: {health['leads_accessible']}")
        else:
            print(f"   [FAIL] {health['message']}")
            print(f"   Codigo: {health['error_code']}")
            print(f"   Detalle tecnico: {health['error']}")
            all_checks_passed = False

        print("\n2. Verificando tablas requeridas...")
        tables = check_required_tables()
        print(f"   Encontradas: {len(tables['found'])}/{len(tables['required'])}")
        for table_name in tables["found"]:
            print(f"     [OK] {table_name}")
        for table_name in tables["missing"]:
            print(f"     [FAIL] {table_name}")
            all_checks_passed = False

        print("\n3. Verificando catalogos...")
        catalogs = check_catalogs()
        print(f"   AFP activas: {catalogs['afp_count']}")
        print(f"   Generos activos: {catalogs['genero_count']}")
        print(f"   Estados civiles activos: {catalogs['estado_civil_count']}")
        if not catalogs["all_ready"]:
            all_checks_passed = False

    except DatabaseAppError as error:
        logger.error(
            "Verification failed | operation=%s | code=%s | detail=%s",
            error.operation,
            error.code,
            error.technical_message,
        )
        print("\n[FAIL] Fallo la verificacion operativa")
        print(f"   {error.user_message}")
        print(f"   Detalle tecnico: {error.technical_message}")
        all_checks_passed = False
    finally:
        close_pool()

    print("\n" + "=" * 70)
    if all_checks_passed:
        print("[OK] TODAS LAS VERIFICACIONES PASARON CORRECTAMENTE")
    else:
        print("[FAIL] ALGUNAS VERIFICACIONES FALLARON")
    print("=" * 70 + "\n")

    return all_checks_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
