"""Script para verificar conexión a PostgreSQL y estado de catálogos."""

import sys
import psycopg
from app.config.settings import settings

def test_database_connection():
    """Verificar conexión a base de datos."""
    print("\n" + "="*70)
    print("VALIDACIÓN 1: Conexión a PostgreSQL")
    print("="*70)
    
    try:
        # Construir conexión string para psycopg (sin el prefijo SQLAlchemy)
        conn_str = (
            f"postgresql://{settings.database_user}:{settings.database_password}@"
            f"{settings.database_host}:{settings.database_port}/{settings.database_name}"
        )
        print(f"Host: {settings.database_host}:{settings.database_port}")
        print(f"Base de datos: {settings.database_name}")
        print(f"Usuario: {settings.database_user}")
        
        conn = psycopg.connect(conn_str)
        print("✓ Conexión exitosa a PostgreSQL")
        
        # Ver la versión de PostgreSQL
        result = conn.execute("SELECT version()").fetchone()
        version_str = result[0].split(",")[0] if result else "Unknown"
        print(f"✓ {version_str}")
        
        # Verificar si existen los catálogos
        query = """
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'tpi' 
        AND table_name IN ('catalogo_genero', 'catalogo_estado_civil', 'catalogo_afp')
        """
        result = conn.execute(query).fetchall()
        print(f"\n✓ Catálogos encontrados: {len(result)} de 3 requeridos")
        
        catalogs = ['catalogo_genero', 'catalogo_estado_civil', 'catalogo_afp']
        found_catalogs = [row[0] for row in result]
        
        for catalog in catalogs:
            if catalog in found_catalogs:
                # Contar registros
                count = conn.execute(f"SELECT COUNT(*) FROM tpi.{catalog}").fetchone()[0]
                print(f"  ✓ {catalog}: {count} registros")
            else:
                print(f"  ✗ {catalog}: NO ENCONTRADO")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"✗ Error de conexión: {type(e).__name__}")
        print(f"  Detalle: {e}")
        return False


def test_solicitud_tables():
    """Verificar tablas de solicitud."""
    print("\n" + "="*70)
    print("VALIDACIÓN 2: Tablas de Solicitud")
    print("="*70)
    
    try:
        # Construir conexión string para psycopg
        conn_str = (
            f"postgresql://{settings.database_user}:{settings.database_password}@"
            f"{settings.database_host}:{settings.database_port}/{settings.database_name}"
        )
        conn = psycopg.connect(conn_str)
        
        query = """
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'tpi' 
        AND table_name IN ('persona', 'solicitud_simulacion')
        """
        result = conn.execute(query).fetchall()
        found_tables = [row[0] for row in result]
        
        print(f"✓ Tablas encontradas: {len(found_tables)} de 2 requeridas")
        for table in found_tables:
            count = conn.execute(f"SELECT COUNT(*) FROM tpi.{table}").fetchone()[0]
            print(f"  ✓ {table}: {count} registros existentes")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


if __name__ == "__main__":
    success1 = test_database_connection()
    success2 = test_solicitud_tables()
    
    if success1 and success2:
        print("\n" + "="*70)
        print("✓ Todas las validaciones de conexión pasaron")
        print("="*70 + "\n")
        sys.exit(0)
    else:
        print("\n" + "="*70)
        print("✗ Algunas validaciones fallaron")
        print("="*70 + "\n")
        sys.exit(1)
