"""Script para explorar estructura de tablas."""

import psycopg
from app.config.settings import settings

def explore_table_structure():
    """Explorar estructura de las tablas de catálogos."""
    print("\n" + "="*70)
    print("EXPLORACIÓN: Estructura de Tablas de Catálogos")
    print("="*70)
    
    try:
        conn = psycopg.connect(
            host=settings.database_host,
            port=settings.database_port,
            user=settings.database_user,
            password=settings.database_password,
            dbname=settings.database_name
        )
        
        tables = ['catalogo_genero', 'catalogo_estado_civil', 'catalogo_afp']
        
        for table in tables:
            print(f"\nTabla: tpi.{table}")
            print("-" * 70)
            
            # Obtener columnas
            query = f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'tpi' AND table_name = '{table}'
            ORDER BY ordinal_position
            """
            result = conn.execute(query).fetchall()
            
            print(f"Columnas ({len(result)}):")
            for row in result:
                print(f"  - {row[0]} ({row[1]})")
            
            # Mostrar datos de ejemplo
            sample_query = f"SELECT * FROM tpi.{table} LIMIT 2"
            sample = conn.execute(sample_query).fetchall()
            
            if sample:
                print(f"\nEjemplos (primeros 2):")
                for i, row in enumerate(sample):
                    print(f"  Registro {i+1}: {row}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    explore_table_structure()
