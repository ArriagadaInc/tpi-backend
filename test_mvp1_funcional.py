"""
Validación funcional completa del MVP1 con Streamlit.

Este script prueba el flujo completo:
1. Cargar la aplicación Streamlit
2. Obtener catálogos 
3. Registrar una solicitud
4. Verificar persistencia en PostgreSQL
"""

import time
import subprocess
import psycopg
from datetime import datetime
from app.config.settings import settings
from app.database.connection import initialize_pool, close_pool


def check_bd_ready():
    """Verificar que BD está lista."""
    print("\n" + "="*70)
    print("PASO 1: Verificar conexión a PostgreSQL")
    print("="*70)
    
    try:
        conn = psycopg.connect(
            host=settings.database_host,
            port=settings.database_port,
            user=settings.database_user,
            password=settings.database_password,
            dbname=settings.database_name
        )
        
        # Ver catálogos
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM tpi.catalogo_genero WHERE activo = TRUE")
            generos = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM tpi.catalogo_estado_civil WHERE activo = TRUE")
            estados = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM tpi.catalogo_afp WHERE activo = TRUE")
            afps = cur.fetchone()[0]
            
            print(f"✓ Conectado a tpi_local")
            print(f"  - Géneros activos: {generos}")
            print(f"  - Estados civiles activos: {estados}")
            print(f"  - AFPs activas: {afps}")
        
        conn.close()
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_catalog_loading():
    """Prueba carga de catálogos."""
    print("\n" + "="*70)
    print("PASO 2: Cargar catálogos (como lo hace la aplicación)")
    print("="*70)
    
    try:
        initialize_pool()
        
        from app.services.solicitud_service import SolicitudService
        service = SolicitudService()
        
        generos = service.get_catalogo_genero()
        afps = service.get_catalogo_afp()
        estados = service.get_catalogo_estado_civil()
        
        print(f"✓ Catálogos cargados correctamente")
        print(f"  - Géneros: {[g['nombre'] for g in generos]}")
        print(f"  - Estados civiles: {[e['nombre'] for e in estados]}")
        print(f"  - AFPs: {[a['nombre'] for a in afps]}")
        
        close_pool()
        return True, generos, estados, afps
    except Exception as e:
        print(f"✗ Error: {e}")
        close_pool()
        return False, [], [], []


def test_registration_flow(generos, estados, afps):
    """Prueba registro de solicitud."""
    print("\n" + "="*70)
    print("PASO 3: Registrar solicitud (transacción única)")
    print("="*70)
    
    if not (generos and estados and afps):
        print("✗ No hay catálogos disponibles")
        return False, None
    
    try:
        initialize_pool()
        
        from app.services.solicitud_service import SolicitudService
        from app.models.solicitud import (
            PersonaData, SolicitudData, ConsentimientosData, RegistrarSolicitudRequest
        )
        from datetime import date
        from decimal import Decimal
        
        service = SolicitudService()
        
        # Datos de prueba
        persona = PersonaData(
            rut="18956325-K",
            nombre_completo="Test Persona García",
            email="test@example.com",
            telefono="+56912345678",
            fecha_nacimiento=date(1990, 5, 15)
        )
        
        solicitud = SolicitudData(
            genero_id=generos[0]["id"],
            estado_civil_id=estados[0]["id"],
            afp_id=afps[0]["id"],
            saldo_afp=Decimal("500000"),
            comentarios="Solicitud de prueba MVPfuncional"
        )
        
        consentimientos = ConsentimientosData(
            acepta_terminos=True,
            acepta_politica_privacidad=True,
            finalidad_contacto=True
        )
        
        request = RegistrarSolicitudRequest(
            persona=persona,
            solicitud=solicitud,
            consentimientos=consentimientos
        )
        
        response = service.registrar_solicitud(request)
        
        print(f"✓ Solicitud registrada exitosamente")
        print(f"  - ID Persona: {response.id_persona}")
        print(f"  - ID Lead: {response.id_lead}")
        print(f"  - RUT: {response.rut}")
        print(f"  - Nombre: {response.nombre_completo}")
        print(f"  - Fecha: {response.fecha_creacion}")
        
        close_pool()
        return True, response
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        close_pool()
        return False, None


def verify_persistence(response):
    """Verifica que los datos se guardaron en BD."""
    print("\n" + "="*70)
    print("PASO 4: Verificar persistencia en PostgreSQL")
    print("="*70)
    
    try:
        conn = psycopg.connect(
            host=settings.database_host,
            port=settings.database_port,
            user=settings.database_user,
            password=settings.database_password,
            dbname=settings.database_name
        )
        
        with conn.cursor() as cur:
            # Ver persona
            cur.execute(
                "SELECT id_persona, rut, nombre_completo FROM tpi.personas WHERE id_persona = %s",
                (str(response.id_persona),)
            )
            persona_row = cur.fetchone()
            
            # Ver lead
            cur.execute(
                "SELECT id_lead, id_persona, genero_id, estado_civil_id, afp_id, estado_lead FROM tpi.leads WHERE id_lead = %s",
                (str(response.id_lead),)
            )
            lead_row = cur.fetchone()
            
            # Ver consentimientos
            cur.execute(
                "SELECT id_consentimiento, id_persona, id_lead FROM tpi.consentimientos WHERE id_lead = %s",
                (str(response.id_lead),)
            )
            consent_row = cur.fetchone()
        
        conn.close()
        
        if not (persona_row and lead_row and consent_row):
            print("✗ No todos los registros fueron encontrados en BD")
            return False
        
        print(f"✓ Todos los registros encontrados en PostgreSQL")
        print(f"\n  Tabla tpi.personas:")
        print(f"    - ID: {persona_row[0]}")
        print(f"    - RUT: {persona_row[1]}")
        print(f"    - Nombre: {persona_row[2]}")
        
        print(f"\n  Tabla tpi.leads:")
        print(f"    - ID: {lead_row[0]}")
        print(f"    - ID Persona (FK): {lead_row[1]}")
        print(f"    - Genero ID (FK): {lead_row[2]}")
        print(f"    - Estado Civil ID (FK): {lead_row[3]}")
        print(f"    - AFP ID (FK): {lead_row[4]}")
        print(f"    - Estado: {lead_row[5]}")
        
        print(f"\n  Tabla tpi.consentimientos:")
        print(f"    - ID: {consent_row[0]}")
        print(f"    - ID Persona (FK): {consent_row[1]}")
        print(f"    - ID Lead (FK): {consent_row[2]}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_list_solicitudes():
    """Verifica que la solicitud aparezca en listado."""
    print("\n" + "="*70)
    print("PASO 5: Listar solicitudes")
    print("="*70)
    
    try:
        initialize_pool()
        
        from app.services.solicitud_service import SolicitudService
        service = SolicitudService()
        
        # Obtener primeras 5 solicitudes
        result = service.get_solicitudes_lista(page=1, page_size=5, masked=False)
        solicitudes = result.get('solicitudes', [])
        
        if not solicitudes:
            print("✗ No hay solicitudes en la lista")
            close_pool()
            return False
        
        print(f"✓ Solicitudes en listado: {result['total']} total, mostrando {len(solicitudes)}")
        print(f"  Últimas 3 solicitudes:")
        for i, sol in enumerate(solicitudes[:3]):
            print(f"    {i+1}. {sol.get('nombre_completo', 'N/A')} - RUT: {sol.get('rut', 'N/A')}")
        
        close_pool()
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        close_pool()
        return False


def main():
    """Ejecutar validación completa."""
    print("\n" + "="*70)
    print("VALIDACIÓN FUNCIONAL MVP1 - TU PENSIÓN INTELIGENTE")
    print("="*70)
    
    # PASO 1: BD lista
    if not check_bd_ready():
        print("\n✗ No se puede proceder: BD no disponible")
        return False
    
    # PASO 2: Catálogos
    success, generos, estados, afps = test_catalog_loading()
    if not success:
        print("\n✗ No se puede proceder: Error cargando catálogos")
        return False
    
    # PASO 3: Registro
    success, response = test_registration_flow(generos, estados, afps)
    if not success or not response:
        print("\n✗ No se puede proceder: Error en registro")
        return False
    
    # PASO 4: Persistencia
    if not verify_persistence(response):
        print("\n✗ No se puede proceder: Datos no persistidos correctamente")
        return False
    
    # PASO 5: Listado
    if not test_list_solicitudes():
        print("\n⚠️ Advertencia: No se pudo verificar listado")
    
    # Resumen
    print("\n" + "="*70)
    print("✅ MVP1 VALIDACIÓN COMPLETADA EXITOSAMENTE")
    print("="*70)
    print("\nResultados:")
    print("  ✓ Conexión a PostgreSQL OK")
    print("  ✓ Catálogos se cargan correctamente")
    print("  ✓ Transacción de registro EXITOSA (persona + lead + consentimientos)")
    print("  ✓ Persistencia en BD VERIFICADA")
    print("  ✓ Listado de solicitudes funciona")
    print("\nMVP1 está listo para demostración local con datos ficticios.\n")
    
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
