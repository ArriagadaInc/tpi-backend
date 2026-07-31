"""
Capa de acceso a datos para Solicitudes de Simulación.

Responsabilidades:
- Insertar personas, solicitudes y consentimientos
- Consultar solicitudes con datos relacionados
- Mantener integridad referencial y transaccional
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from app.database.connection import get_db_connection
from app.models.solicitud import (
    ConsentimientosData,
    PersonaData,
    SolicitudData,
    SolicitudResponse,
)


class SolicitudRepository:
    """Repositorio para operaciones de solicitudes en la BD."""

    @staticmethod
    def get_persona_by_rut(rut: str) -> Optional[dict[str, Any]]:
        """
        Obtiene una persona por su RUT.

        Args:
            rut: RUT normalizado (ej: "12345678-5")

        Returns:
            Dict con datos de persona o None si no existe
        """
        query = """
            SELECT id_persona, rut, nombre_completo, email, telefono, 
                   fecha_nacimiento, created_at
            FROM tpi.personas
            WHERE rut = %s
            LIMIT 1
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (rut,))
                row = cur.fetchone()
                return dict(row) if row else None

    @staticmethod
    def create_persona(persona_data: PersonaData) -> UUID:
        """
        Crea una nueva persona en la BD.

        Si la persona ya existe (por RUT), retorna su ID existente.

        Args:
            persona_data: Datos validados de la persona

        Returns:
            UUID del id_persona creado o existente

        Raises:
            Exception: Si falla la inserción en BD
        """
        # Verificar si persona ya existe
        existing = SolicitudRepository.get_persona_by_rut(persona_data.rut)
        if existing:
            return UUID(str(existing["id_persona"]))

        # Insertar nueva persona
        query = """
            INSERT INTO tpi.personas 
                (rut, nombre_completo, email, telefono, fecha_nacimiento, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id_persona
        """
        params = (
            persona_data.rut,
            persona_data.nombre_completo,
            persona_data.email,
            persona_data.telefono,
            persona_data.fecha_nacimiento,
            datetime.now(),
        )

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                row = cur.fetchone()
                conn.commit()
                return UUID(str(row["id_persona"])) if row else None

    @staticmethod
    def create_solicitud(
        persona_data: PersonaData,
        solicitud_data: SolicitudData,
        consentimientos_data: ConsentimientosData,
    ) -> SolicitudResponse:
        """
        Crea una solicitud completa (persona + lead + consentimientos) en transacción.

        Esta operación es atómica: o se insertan todos los registros, o ninguno.

        Args:
            persona_data: Datos validados de persona
            solicitud_data: Datos validados de solicitud
            consentimientos_data: Datos validados de consentimientos

        Returns:
            SolicitudResponse con id_lead y datos de confirmación

        Raises:
            Exception: Si falla cualquier paso de la transacción
        """
        with get_db_connection() as conn:
            try:
                # PASO 1: Crear o recuperar persona
                id_persona = SolicitudRepository.create_persona(persona_data)

                # PASO 2: Crear lead (solicitud)
                query_lead = """
                    INSERT INTO tpi.leads 
                        (id_persona, genero_id, estado_civil_id, afp_id, 
                         saldo_afp, comentarios, estado_lead, fecha_ingreso,
                         origen_lead, fuente_actual, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id_lead
                """
                params_lead = (
                    str(id_persona),
                    str(solicitud_data.genero_id),
                    str(solicitud_data.estado_civil_id),
                    str(solicitud_data.afp_id),
                    solicitud_data.saldo_afp,
                    solicitud_data.comentarios or "",
                    "pendiente",  # estado inicial
                    datetime.now(),  # fecha_ingreso
                    "formulario_streamlit",  # origen_lead
                    "backoffice",  # fuente_actual
                    datetime.now(),  # created_at
                )

                with conn.cursor() as cur:
                    cur.execute(query_lead, params_lead)
                    row = cur.fetchone()
                    id_lead = UUID(str(row["id_lead"])) if row else None

                    if not id_lead:
                        raise Exception("No se pudo crear el lead")

                    # PASO 3: Crear consentimientos
                    query_consent = """
                        INSERT INTO tpi.consentimientos 
                            (id_persona, id_lead, acepta_terminos, acepta_politica_privacidad, 
                             finalidad_contacto, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id_consentimiento
                    """
                    params_consent = (
                        str(id_persona),
                        str(id_lead),
                        consentimientos_data.acepta_terminos,
                        consentimientos_data.acepta_politica_privacidad,
                        consentimientos_data.finalidad_contacto,
                        datetime.now(),
                    )
                    cur.execute(query_consent, params_consent)
                    row = cur.fetchone()

                    if not row:
                        raise Exception("No se pudieron crear los consentimientos")

                    # COMMIT IMPLÍCITO al salir del context manager
                    conn.commit()

                # PASO 4: Retornar respuesta exitosa
                return SolicitudResponse(
                    id_lead=id_lead,
                    id_persona=id_persona,
                    rut=persona_data.rut,
                    nombre_completo=persona_data.nombre_completo,
                    fecha_creacion=datetime.now(),
                    estado_lead="pendiente",
                    mensaje="Solicitud registrada exitosamente",
                )

            except Exception as e:
                conn.rollback()
                raise Exception(f"Error al crear solicitud: {str(e)}") from e

    @staticmethod
    def get_solicitud_by_id(id_lead: UUID) -> Optional[dict[str, Any]]:
        """
        Obtiene una solicitud completa (con datos relacionados) por ID.

        Args:
            id_lead: UUID del lead a consultar

        Returns:
            Dict con datos de solicitud o None si no existe
        """
        query = """
            SELECT 
                l.id_lead,
                l.id_persona,
                p.rut,
                p.nombre_completo,
                p.email,
                p.telefono,
                p.fecha_nacimiento,
                l.genero_id,
                cg.descripcion AS genero,
                l.estado_civil_id,
                cec.descripcion AS estado_civil,
                l.afp_id,
                ca.descripcion AS afp,
                l.saldo_afp,
                l.comentarios,
                l.estado_lead,
                l.created_at,
                c.id_consentimiento,
                c.acepta_terminos,
                c.acepta_politica_privacidad,
                c.finalidad_contacto
            FROM tpi.leads l
            INNER JOIN tpi.personas p ON l.id_persona = p.id_persona
            LEFT JOIN tpi.catalogo_genero cg ON l.genero_id = cg.id_genero
            LEFT JOIN tpi.catalogo_estado_civil cec ON l.estado_civil_id = cec.id_estado_civil
            LEFT JOIN tpi.catalogo_afp ca ON l.afp_id = ca.id_afp
            LEFT JOIN tpi.consentimientos c ON l.id_lead = c.id_lead
            WHERE l.id_lead = %s
            LIMIT 1
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (str(id_lead),))
                row = cur.fetchone()
                return dict(row) if row else None

    @staticmethod
    def get_all_solicitudes(
        limit: int = 100, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Obtiene todas las solicitudes con paginación.

        Args:
            limit: Número máximo de registros
            offset: Desplazamiento para paginación

        Returns:
            Tupla (lista de solicitudes, total de registros)
        """
        query_count = "SELECT COUNT(*) as total FROM tpi.leads"
        query_data = """
            SELECT 
                l.id_lead,
                l.id_persona,
                p.rut,
                p.nombre_completo,
                p.email,
                p.telefono,
                l.genero_id,
                cg.descripcion AS genero,
                l.estado_civil_id,
                cec.descripcion AS estado_civil,
                l.afp_id,
                ca.descripcion AS afp,
                l.saldo_afp,
                l.estado_lead,
                l.created_at
            FROM tpi.leads l
            INNER JOIN tpi.personas p ON l.id_persona = p.id_persona
            LEFT JOIN tpi.catalogo_genero cg ON l.genero_id = cg.id_genero
            LEFT JOIN tpi.catalogo_estado_civil cec ON l.estado_civil_id = cec.id_estado_civil
            LEFT JOIN tpi.catalogo_afp ca ON l.afp_id = ca.id_afp
            ORDER BY l.created_at DESC
            LIMIT %s OFFSET %s
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Obtener total
                cur.execute(query_count)
                total = cur.fetchone()["total"] if cur.fetchone() else 0

                # Obtener datos paginados
                cur.execute(query_data, (limit, offset))
                rows = cur.fetchall()
                return [dict(row) for row in rows], total

    @staticmethod
    def get_solicitudes_by_rut(rut: str) -> list[dict[str, Any]]:
        """
        Obtiene todas las solicitudes de una persona por RUT.

        Args:
            rut: RUT normalizado

        Returns:
            Lista de solicitudes
        """
        query = """
            SELECT 
                l.id_lead,
                l.id_persona,
                p.rut,
                p.nombre_completo,
                l.estado_lead,
                l.saldo_afp,
                l.created_at
            FROM tpi.leads l
            INNER JOIN tpi.personas p ON l.id_persona = p.id_persona
            WHERE p.rut = %s
            ORDER BY l.created_at DESC
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (rut,))
                rows = cur.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    def get_active_afp() -> list[dict[str, Any]]:
        """Obtiene todos los AFP activos."""
        query = "SELECT id_afp, descripcion FROM tpi.catalogo_afp WHERE estado = 1 ORDER BY descripcion"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    def get_active_genero() -> list[dict[str, Any]]:
        """Obtiene todos los géneros activos."""
        query = "SELECT id_genero, descripcion FROM tpi.catalogo_genero WHERE estado = 1 ORDER BY descripcion"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    def get_active_estado_civil() -> list[dict[str, Any]]:
        """Obtiene todos los estados civiles activos."""
        query = "SELECT id_estado_civil, descripcion FROM tpi.catalogo_estado_civil WHERE estado = 1 ORDER BY descripcion"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                return [dict(row) for row in rows]
