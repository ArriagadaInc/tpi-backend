"""
Health check y validación de conexión a PostgreSQL.

Verifica que la base de datos esté accesible y que el esquema sea compatible.
"""

import logging
from typing import Dict, Any

from app.database.connection import get_db_connection
from app.config.settings import settings

logger = logging.getLogger(__name__)


def check_database_connection() -> Dict[str, Any]:
    """
    Verificar que PostgreSQL esté accesible.
    
    Returns:
        Dict con keys:
        - "connected": bool
        - "message": str (descripción del estado)
        - "error": str (si connected=False, descripción del error)
        - "database": str (nombre de la base de datos)
        - "schema": str (esquema TPI)
    
    Ejemplo de uso:
        health = check_database_connection()
        if health["connected"]:
            st.success("✅ Base de datos conectada")
        else:
            st.error(f"❌ {health['message']}")
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Query de prueba simple
                cur.execute("SELECT 1 AS test")
                result = cur.fetchone()
                
                if result is None or result.get("test") != 1:
                    return {
                        "connected": False,
                        "message": "Base de datos no disponible",
                        "error": "Respuesta inesperada del servidor",
                        "database": settings.database_name,
                        "schema": settings.database_schema,
                    }
        
        return {
            "connected": True,
            "message": "Base de datos conectada correctamente",
            "error": None,
            "database": settings.database_name,
            "schema": settings.database_schema,
        }
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error verificando conexión a BD: {error_msg}")
        
        return {
            "connected": False,
            "message": "No fue posible conectar con la base de datos",
            "error": error_msg,
            "database": settings.database_name,
            "schema": settings.database_schema,
        }


def check_schema_exists() -> Dict[str, Any]:
    """
    Verificar que el esquema TPI exista en PostgreSQL.
    
    Returns:
        Dict con keys:
        - "exists": bool
        - "message": str
        - "tables_count": int (cantidad de tablas en el esquema)
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) as count FROM information_schema.tables
                    WHERE table_schema = %s
                    """,
                    (settings.database_schema,),
                )
                result = cur.fetchone()
                tables_count = result.get("count", 0) if result else 0
                
                return {
                    "exists": tables_count > 0,
                    "message": f"Esquema '{settings.database_schema}' con {tables_count} tablas",
                    "tables_count": tables_count,
                }
    
    except Exception as e:
        logger.error(f"Error verificando esquema: {e}")
        return {
            "exists": False,
            "message": f"Error verificando esquema: {str(e)}",
            "tables_count": 0,
        }


def check_required_tables() -> Dict[str, Any]:
    """
    Verificar que existan las tablas requeridas para el MVP.
    
    Returns:
        Dict con keys:
        - "all_present": bool (todos las tablas requeridas existen)
        - "required": list[str]
        - "found": list[str]
        - "missing": list[str]
    """
    required_tables = [
        "personas",
        "leads",
        "consentimientos",
        "catalogo_afp",
        "catalogo_genero",
        "catalogo_estado_civil",
    ]
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = %s
                    """,
                    (settings.database_schema,),
                )
                existing_tables = {row["table_name"] for row in cur.fetchall()}
        
        found = [t for t in required_tables if t in existing_tables]
        missing = [t for t in required_tables if t not in existing_tables]
        
        return {
            "all_present": len(missing) == 0,
            "required": required_tables,
            "found": found,
            "missing": missing,
        }
    
    except Exception as e:
        logger.error(f"Error verificando tablas: {e}")
        return {
            "all_present": False,
            "required": required_tables,
            "found": [],
            "missing": required_tables,
        }


def check_catalogs() -> Dict[str, Any]:
    """
    Verificar que los catálogos tengan datos.
    
    Returns:
        Dict con keys:
        - "all_ready": bool
        - "afp_count": int
        - "genero_count": int
        - "estado_civil_count": int
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                queries = {
                    "afp_count": f"SELECT COUNT(*) as cnt FROM {settings.database_schema}.catalogo_afp WHERE activo=TRUE",
                    "genero_count": f"SELECT COUNT(*) as cnt FROM {settings.database_schema}.catalogo_genero WHERE activo=TRUE",
                    "estado_civil_count": f"SELECT COUNT(*) as cnt FROM {settings.database_schema}.catalogo_estado_civil WHERE activo=TRUE",
                }
                
                results = {}
                for key, query in queries.items():
                    cur.execute(query)
                    row = cur.fetchone()
                    results[key] = row.get("cnt", 0) if row else 0
        
        all_ready = all(v > 0 for v in results.values())
        
        return {
            "all_ready": all_ready,
            **results,
        }
    
    except Exception as e:
        logger.error(f"Error verificando catálogos: {e}")
        return {
            "all_ready": False,
            "afp_count": 0,
            "genero_count": 0,
            "estado_civil_count": 0,
        }


def full_health_check() -> Dict[str, Any]:
    """
    Ejecutar un health check completo de la aplicación.
    
    Verifica:
    1. Conexión a PostgreSQL
    2. Existencia del esquema
    3. Existencia de tablas requeridas
    4. Catálogos con datos
    
    Returns:
        Dict con "all_ready" y "connected" a nivel superior (usados por la
        UI de Streamlit y los tests) además del detalle de cada check.
    """
    connection = check_database_connection()
    schema = check_schema_exists()
    tables = check_required_tables()
    catalogs = check_catalogs()
    
    all_ready = (
        connection["connected"]
        and schema["exists"]
        and tables["all_present"]
        and catalogs["all_ready"]
    )
    
    return {
        "all_ready": all_ready,
        "connected": connection["connected"],
        "connection": connection,
        "schema": schema,
        "tables": tables,
        "catalogs": catalogs,
    }
