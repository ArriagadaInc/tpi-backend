"""Script para verificar configuración de PostgreSQL."""

import os
import psycopg
from app.config.settings import settings

def check_postgres_users():
    """Ver usuarios de PostgreSQL."""
    print("\n" + "="*70)
    print("VERIFICACIÓN: Usuarios de PostgreSQL")
    print("="*70)
    
    try:
        # Conectar usando configuración de settings (variables de entorno)
        password = settings.database_password or os.environ.get('DATABASE_PASSWORD', '')
        conn = psycopg.connect(
            host=settings.database_host,
            port=settings.database_port,
            user=settings.database_user,
            password=password,
            dbname='postgres'
        )
        print("✓ Conectado como postgres")
        
        # Ver usuarios
        result = conn.execute("SELECT usename, usesuper FROM pg_user").fetchall()
        print(f"\nUsuarios en PostgreSQL ({len(result)} total):")
        for row in result:
            super_flag = "SUPERUSER" if row[1] else ""
            print(f"  - {row[0]} {super_flag}")
        
        # Ver bases de datos
        result = conn.execute("SELECT datname FROM pg_database WHERE datname NOT LIKE 'template%'").fetchall()
        print(f"\nBases de datos ({len(result)} total):")
        for row in result:
            print(f"  - {row[0]}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

if __name__ == "__main__":
    check_postgres_users()
