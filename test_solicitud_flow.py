"""Script para registrar y validar una solicitud ficticia completa."""

import sys
import psycopg
from datetime import date, datetime
from uuid import UUID

from app.config.settings import settings
from app.database.connection import initialize_pool, close_pool
from app.models.solicitud import PersonaData, SolicitudData, ConsentimientosData
from app.repositories.solicitud_repository import SolicitudRepository

def register_and_verify_solicitud():
    """Registrar una solicitud ficticia y verificar que se insertó correctamente."""
    print("\n" + "="*70)
    print("VALIDACIÓN 4: Registro y Verificación de Solicitud")
    print("="*70)
    
    try:
        # Inicializar el pool de conexiones
        initialize_pool()
        
        # Datos ficticios para la solicitud
        persona_data = PersonaData(
            rut="18.956.325-K",
            nombre_completo="Juan Pérez García",
            email="juan.perez@example.com",
            telefono="+56987654321",
            fecha_nacimiento=date(1985, 3, 15)
        )
        
        # Obtener IDs de catálogos
        conn_str = (
            f"postgresql://{settings.database_user}:{settings.database_password}@"
            f"{settings.database_host}:{settings.database_port}/{settings.database_name}"
        )
        conn = psycopg.connect(conn_str)
        
        # Obtener ID de género (Masculino)
        genero_result = conn.execute(
            "SELECT id FROM tpi.catalogo_genero WHERE nombre = 'Masculino' LIMIT 1"
        ).fetchone()
        genero_id = UUID(str(genero_result[0])) if genero_result else None
        
        # Obtener ID de estado civil (Soltero)
        estado_civil_result = conn.execute(
            "SELECT id FROM tpi.catalogo_estado_civil WHERE nombre = 'Soltero/a' LIMIT 1"
        ).fetchone()
        estado_civil_id = UUID(str(estado_civil_result[0])) if estado_civil_result else None
        
        # Obtener ID de AFP (primera disponible)
        afp_result = conn.execute(
            "SELECT id FROM tpi.catalogo_afp LIMIT 1"
        ).fetchone()
        afp_id = UUID(str(afp_result[0])) if afp_result else None
        
        conn.close()
        
        if not all([genero_id, estado_civil_id, afp_id]):
            print("✗ No se encontraron catálogos necesarios")
            return False
        
        print(f"\n✓ Catálogos identificados:")
        print(f"  - Género ID: {genero_id}")
        print(f"  - Estado Civil ID: {estado_civil_id}")
        print(f"  - AFP ID: {afp_id}")
        
        # Crear solicitud
        solicitud_data = SolicitudData(
            genero_id=genero_id,
            estado_civil_id=estado_civil_id,
            afp_id=afp_id,
            saldo_afp=1500000.00,
            comentarios="Solicitud de prueba para MVP"
        )
        
        consentimientos_data = ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True
        )
        
        # Registrar solicitud usando el repositorio
        print(f"\nRegistrando solicitud...")
        response = SolicitudRepository.create_solicitud(
            persona_data,
            solicitud_data,
            consentimientos_data
        )
        
        print(f"✓ Solicitud registrada exitosamente")
        print(f"  - ID Lead: {response.id_lead}")
        print(f"  - ID Persona: {response.id_persona}")
        print(f"  - RUT: {response.rut}")
        print(f"  - Nombre: {response.nombre_completo}")
        print(f"  - Estado: {response.estado_lead}")
        
        # Verificar que se insertó en la BD
        print(f"\nVerificando en PostgreSQL...")
        conn = psycopg.connect(conn_str)
        
        # Verificar persona
        persona_check = conn.execute(
            f"SELECT rut, nombre_completo, email FROM tpi.personas WHERE id_persona = %s",
            (str(response.id_persona),)
        ).fetchone()
        
        if persona_check:
            print(f"✓ Persona encontrada en BD:")
            print(f"  - RUT: {persona_check[0]}")
            print(f"  - Nombre: {persona_check[1]}")
            print(f"  - Email: {persona_check[2]}")
        else:
            print(f"✗ Persona NO encontrada en BD")
            conn.close()
            return False
        
        # Verificar lead
        lead_check = conn.execute(
            f"SELECT id_lead, id_persona, genero_id, estado_civil_id, afp_id, estado_lead FROM tpi.leads WHERE id_lead = %s",
            (str(response.id_lead),)
        ).fetchone()
        
        if lead_check:
            print(f"✓ Lead encontrado en BD:")
            print(f"  - ID Lead: {lead_check[0]}")
            print(f"  - ID Persona: {lead_check[1]}")
            print(f"  - Género ID: {lead_check[2]}")
            print(f"  - Estado Civil ID: {lead_check[3]}")
            print(f"  - AFP ID: {lead_check[4]}")
            print(f"  - Estado: {lead_check[5]}")
        else:
            print(f"✗ Lead NO encontrado en BD")
            conn.close()
            return False
        
        # Verificar consentimientos
        consent_check = conn.execute(
            f"SELECT id_consentimiento, acepta_terminos, acepta_politica_privacidad FROM tpi.consentimientos WHERE id_lead = %s",
            (str(response.id_lead),)
        ).fetchone()
        
        if consent_check:
            print(f"✓ Consentimientos encontrados en BD:")
            print(f"  - ID Consentimiento: {consent_check[0]}")
            print(f"  - Acepta Términos: {consent_check[1]}")
            print(f"  - Acepta Política: {consent_check[2]}")
        else:
            print(f"✗ Consentimientos NO encontrados en BD")
            conn.close()
            return False
        
        conn.close()
        close_pool()
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        close_pool()
        return False

if __name__ == "__main__":
    success = register_and_verify_solicitud()
    sys.exit(0 if success else 1)
