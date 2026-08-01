"""Script para listar todas las tablas en el esquema tpi."""

import psycopg
from app.config.settings import settings

def list_tables():
    """Listar todas las tablas en el esquema tpi."""
    print("\n" + "="*70)
    print("VALIDACIÓN: Tablas en esquema TPI")
    print("="*70)
    
    try:
        conn = psycopg.connect(
            host=settings.database_host,
            port=settings.database_port,
            user=settings.database_user,
            password=settings.database_password,
            dbname=settings.database_name
        )
        
        query = """
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'tpi'
        ORDER BY table_name
        """
        result = conn.execute(query).fetchall()
        
        print(f"\nTablas encontradas: {len(result)}")
        for row in result:
            table_name = row[0]
            # Contar registros
            count = conn.execute(f"SELECT COUNT(*) FROM tpi.{table_name}").fetchone()[0]
            print(f"  - {table_name}: {count} registros")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

if __name__ == "__main__":
    list_tables()
