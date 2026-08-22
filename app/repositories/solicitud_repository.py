"""
Capa de acceso a datos para Solicitudes de SimulaciÃ³n.

Responsabilidades:
- Insertar personas, solicitudes y consentimientos
- Consultar solicitudes con datos relacionados
- Mantener integridad referencial y transaccional
"""

from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID

from psycopg.errors import ForeignKeyViolation

from app.database.connection import get_db_connection
from app.database.errors import DevLeadCleanupBlockedError
from app.models.idempotency import IdempotencyConflictError, IdempotentSolicitudResult
from app.models.solicitud import (
    ConsentimientosData,
    PersonaData,
    SolicitudData,
    SolicitudResponse,
)


class SolicitudRepository:
    """Repositorio para operaciones de solicitudes en la BD."""

    _CRM_SORT_COLUMNS = {
        "created_at": "l.created_at",
        "nombre_completo": "p.nombre_completo",
        "rut": "p.rut",
        "telefono": "p.telefono",
        "afp": "ca.nombre",
        "saldo_afp": "l.saldo_afp",
        "estado_lead": "l.estado_lead",
    }

    @staticmethod
    def _build_crm_query_filters(
        *,
        search: str | None = None,
        estado_lead: str | None = None,
        afp_id: UUID | None = None,
        genero_id: UUID | None = None,
        estado_civil_id: UUID | None = None,
        date_from: datetime | date | None = None,
        date_to: datetime | date | None = None,
    ) -> tuple[str, list[Any]]:
        """Build the CRM WHERE clause and parameters using whitelisted filters."""
        clauses: list[str] = []
        params: list[Any] = []

        if search:
            search_term = f"%{search.strip()}%"
            clauses.append("""
                (
                    p.rut ILIKE %s
                    OR p.nombre_completo ILIKE %s
                    OR p.email ILIKE %s
                    OR p.telefono ILIKE %s
                    OR l.estado_lead ILIKE %s
                    OR COALESCE(ca.nombre, '') ILIKE %s
                    OR COALESCE(l.comentarios, '') ILIKE %s
                )
                """)
            params.extend([search_term] * 7)

        if estado_lead:
            clauses.append("LOWER(l.estado_lead) = LOWER(%s)")
            params.append(estado_lead.strip())

        if afp_id:
            clauses.append("l.afp_id = %s")
            params.append(str(afp_id))

        if genero_id:
            clauses.append("l.genero_id = %s")
            params.append(str(genero_id))

        if estado_civil_id:
            clauses.append("l.estado_civil_id = %s")
            params.append(str(estado_civil_id))

        if date_from:
            if isinstance(date_from, date) and not isinstance(date_from, datetime):
                date_from = datetime.combine(date_from, time.min, tzinfo=UTC)
            clauses.append("l.created_at >= %s")
            params.append(date_from)

        if date_to:
            if isinstance(date_to, date) and not isinstance(date_to, datetime):
                date_to = datetime.combine(date_to, time.max, tzinfo=UTC)
            clauses.append("l.created_at <= %s")
            params.append(date_to)

        if not clauses:
            return "", params

        return "WHERE " + " AND ".join(clauses), params

    @classmethod
    def _normalize_crm_sort(
        cls,
        sort_by: str | None = None,
        sort_direction: str = "desc",
    ) -> tuple[str, str]:
        column = cls._CRM_SORT_COLUMNS.get((sort_by or "created_at").strip(), "l.created_at")
        direction = "ASC" if sort_direction.strip().lower() == "asc" else "DESC"
        return column, direction

    @staticmethod
    def get_persona_by_rut(rut: str) -> dict[str, Any] | None:
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
            Exception: Si falla la inserciÃ³n en BD
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
                if row is None:
                    raise RuntimeError("PostgreSQL no retornÃ³ el ID de la persona")
                conn.commit()
                return UUID(str(row["id_persona"]))

    @staticmethod
    def create_solicitud(
        persona_data: PersonaData,
        solicitud_data: SolicitudData,
        consentimientos_data: ConsentimientosData,
    ) -> SolicitudResponse:
        """
        Crea una solicitud completa (persona + lead + consentimientos) en transacciÃ³n ÃšNICA.

        Esta operaciÃ³n es atÃ³mica: o se insertan todos los registros, o ninguno.
        Usa UNA SOLA conexiÃ³n y UNA SOLA transacciÃ³n para garantizar consistencia.
        Delega las consultas SQL parametrizadas con placeholders ``%s`` al
        helper transaccional; nunca concatena datos de la solicitud en SQL.

        Args:
            persona_data: Datos validados de persona
            solicitud_data: Datos validados de solicitud
            consentimientos_data: Datos validados de consentimientos

        Returns:
            SolicitudResponse con id_lead y datos de confirmaciÃ³n

        Raises:
            Exception: Si falla cualquier paso de la transacciÃ³n
        """
        with get_db_connection(operation="create_solicitud") as conn:
            try:
                with conn.cursor() as cur:
                    response = SolicitudRepository._create_solicitud_in_cursor(
                        cur, persona_data, solicitud_data, consentimientos_data
                    )
                conn.commit()
                return response
            except Exception:
                conn.rollback()
                raise

    @staticmethod
    def create_solicitud_idempotent(
        persona_data: PersonaData,
        solicitud_data: SolicitudData,
        consentimientos_data: ConsentimientosData,
        *,
        idempotency_key: UUID,
        payload_fingerprint: str,
        expires_at: datetime,
    ) -> IdempotentSolicitudResult:
        """Create one lead per idempotency key in the same database transaction."""
        with get_db_connection(operation="create_solicitud_idempotent") as conn:
            try:
                with conn.cursor() as cur:
                    # Opportunistic cleanup avoids a scheduler in the DEV single instance.
                    cur.execute("DELETE FROM tpi.api_idempotency WHERE expires_at <= NOW()")
                    cur.execute(
                        """
                        INSERT INTO tpi.api_idempotency
                            (idempotency_key, payload_fingerprint, expires_at)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (idempotency_key) DO NOTHING
                        RETURNING idempotency_key
                        """,
                        (str(idempotency_key), payload_fingerprint, expires_at),
                    )
                    reserved = cur.fetchone()
                    if reserved is None:
                        cur.execute(
                            """
                            SELECT payload_fingerprint, lead_id
                            FROM tpi.api_idempotency
                            WHERE idempotency_key = %s
                            FOR UPDATE
                            """,
                            (str(idempotency_key),),
                        )
                        existing = cur.fetchone()
                        if existing is None:
                            raise RuntimeError("No fue posible resolver la solicitud repetida")
                        if existing["payload_fingerprint"] != payload_fingerprint:
                            raise IdempotencyConflictError(
                                "La clave de idempotencia ya fue usada con otra solicitud"
                            )
                        if existing["lead_id"] is None:
                            raise RuntimeError("La solicitud repetida todavia esta en proceso")
                        conn.commit()
                        return IdempotentSolicitudResult(
                            lead_id=UUID(str(existing["lead_id"])), created=False
                        )

                    response = SolicitudRepository._create_solicitud_in_cursor(
                        cur, persona_data, solicitud_data, consentimientos_data
                    )
                    cur.execute(
                        """
                        UPDATE tpi.api_idempotency
                        SET lead_id = %s
                        WHERE idempotency_key = %s
                        """,
                        (str(response.id_lead), str(idempotency_key)),
                    )
                conn.commit()
                return IdempotentSolicitudResult(
                    lead_id=response.id_lead, created=True, response=response
                )
            except Exception:
                conn.rollback()
                raise

    @staticmethod
    def _create_solicitud_in_cursor(
        cur: Any,
        persona_data: PersonaData,
        solicitud_data: SolicitudData,
        consentimientos_data: ConsentimientosData,
    ) -> SolicitudResponse:
        """Persist the shared lead aggregate using the caller's transaction."""
        cur.execute(
            "SELECT id_persona FROM tpi.personas WHERE rut = %s LIMIT 1", (persona_data.rut,)
        )
        existing_row = cur.fetchone()
        if existing_row:
            id_persona = UUID(str(existing_row["id_persona"]))
        else:
            cur.execute(
                """
                INSERT INTO tpi.personas
                    (rut, nombre_completo, email, telefono, fecha_nacimiento, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id_persona
                """,
                (
                    persona_data.rut,
                    persona_data.nombre_completo,
                    persona_data.email,
                    persona_data.telefono,
                    persona_data.fecha_nacimiento,
                    datetime.now(),
                ),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("No se pudo crear la persona")
            id_persona = UUID(str(row["id_persona"]))

        cur.execute(
            """
            INSERT INTO tpi.leads
                (id_persona, genero_id, estado_civil_id, afp_id, saldo_afp, comentarios,
                 estado_lead, fecha_ingreso, origen_lead, fuente_actual, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id_lead
            """,
            (
                str(id_persona),
                str(solicitud_data.genero_id),
                str(solicitud_data.estado_civil_id),
                str(solicitud_data.afp_id),
                solicitud_data.saldo_afp,
                solicitud_data.comentarios or "",
                "pendiente",
                datetime.now(),
                "formulario_streamlit",
                "backoffice",
                datetime.now(),
            ),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("No se pudo crear el lead")
        id_lead = UUID(str(row["id_lead"]))

        cur.execute(
            """
            INSERT INTO tpi.consentimientos
                (id_persona, id_lead, acepta_terminos, acepta_politica_privacidad,
                 finalidad_contacto, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id_consentimiento
            """,
            (
                str(id_persona),
                str(id_lead),
                consentimientos_data.acepta_terminos,
                consentimientos_data.acepta_politica_privacidad,
                consentimientos_data.finalidad_contacto,
                datetime.now(),
            ),
        )
        if cur.fetchone() is None:
            raise RuntimeError("No se pudieron crear los consentimientos")

        return SolicitudResponse(
            id_lead=id_lead,
            id_persona=id_persona,
            rut=persona_data.rut,
            nombre_completo=persona_data.nombre_completo,
            fecha_creacion=datetime.now(),
            estado_lead="pendiente",
            mensaje="Solicitud registrada exitosamente",
        )

    @staticmethod
    def get_solicitud_by_id(id_lead: UUID) -> dict[str, Any] | None:
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
                cg.nombre AS genero,
                l.estado_civil_id,
                cec.nombre AS estado_civil,
                l.afp_id,
                ca.nombre AS afp,
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
            LEFT JOIN tpi.catalogo_genero cg ON l.genero_id = cg.id
            LEFT JOIN tpi.catalogo_estado_civil cec ON l.estado_civil_id = cec.id
            LEFT JOIN tpi.catalogo_afp ca ON l.afp_id = ca.id
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
    def test_lead_exists(id_lead: UUID) -> bool:
        """Return whether a lead exists without exposing its contents."""
        query = "SELECT 1 FROM tpi.leads WHERE id_lead = %s"
        with get_db_connection(operation="test_lead_exists") as conn:
            with conn.cursor() as cur:
                cur.execute(query, (str(id_lead),))
                return cur.fetchone() is not None

    @staticmethod
    def delete_test_lead(id_lead: UUID) -> bool:
        """Delete a DEV test lead and its consent records in one transaction.

        The operation intentionally does not remove personas. RDS DEV has
        additional foreign keys from operational tables that can reference a
        persona, and the application role must not receive broad DELETE access.
        """
        with get_db_connection(operation="delete_test_lead") as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id_persona FROM tpi.leads WHERE id_lead = %s FOR UPDATE",
                        (str(id_lead),),
                    )
                    if cur.fetchone() is None:
                        return False

                    cur.execute(
                        "DELETE FROM tpi.consentimientos WHERE id_lead = %s",
                        (str(id_lead),),
                    )
                    cur.execute(
                        "DELETE FROM tpi.leads WHERE id_lead = %s RETURNING id_lead",
                        (str(id_lead),),
                    )
                    if cur.fetchone() is None:
                        raise RuntimeError("The test lead disappeared during cleanup")

                conn.commit()
                return True
            except ForeignKeyViolation as exc:
                conn.rollback()
                raise DevLeadCleanupBlockedError(
                    "Test lead has operational dependencies",
                    operation="delete_test_lead",
                ) from exc
            except Exception:
                conn.rollback()
                raise

    @staticmethod
    def get_all_solicitudes(limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        """
        Obtiene todas las solicitudes con paginaciÃ³n.

        Args:
            limit: NÃºmero mÃ¡ximo de registros
            offset: Desplazamiento para paginaciÃ³n

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
                cg.nombre AS genero,
                l.estado_civil_id,
                cec.nombre AS estado_civil,
                l.afp_id,
                ca.nombre AS afp,
                l.saldo_afp,
                l.estado_lead,
                l.created_at
            FROM tpi.leads l
            INNER JOIN tpi.personas p ON l.id_persona = p.id_persona
            LEFT JOIN tpi.catalogo_genero cg ON l.genero_id = cg.id
            LEFT JOIN tpi.catalogo_estado_civil cec ON l.estado_civil_id = cec.id
            LEFT JOIN tpi.catalogo_afp ca ON l.afp_id = ca.id
            ORDER BY l.created_at DESC
            LIMIT %s OFFSET %s
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Obtener total
                cur.execute(query_count)
                total_row = cur.fetchone()
                total = total_row["total"] if total_row else 0

                # Obtener datos paginados
                cur.execute(query_data, (limit, offset))
                rows = cur.fetchall()
                return [dict(row) for row in rows], total

    @classmethod
    def get_crm_solicitudes(
        cls,
        limit: int = 100,
        offset: int = 0,
        *,
        search: str | None = None,
        estado_lead: str | None = None,
        afp_id: UUID | None = None,
        genero_id: UUID | None = None,
        estado_civil_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        sort_by: str | None = None,
        sort_direction: str = "desc",
    ) -> tuple[list[dict[str, Any]], int]:
        """Return a CRM-ready lead board using only the current schema."""
        where_clause, where_params = cls._build_crm_query_filters(
            search=search,
            estado_lead=estado_lead,
            afp_id=afp_id,
            genero_id=genero_id,
            estado_civil_id=estado_civil_id,
            date_from=date_from,
            date_to=date_to,
        )
        order_column, direction = cls._normalize_crm_sort(sort_by, sort_direction)
        query_count = f"""
            SELECT COUNT(*) AS total
            FROM tpi.leads l
            INNER JOIN tpi.personas p ON l.id_persona = p.id_persona
            LEFT JOIN tpi.catalogo_afp ca ON l.afp_id = ca.id
            {where_clause}
        """
        query_data = f"""
            SELECT
                l.id_lead,
                l.id_persona,
                p.rut,
                p.nombre_completo,
                p.email,
                p.telefono,
                l.genero_id,
                cg.nombre AS genero,
                l.estado_civil_id,
                cec.nombre AS estado_civil,
                l.afp_id,
                ca.nombre AS afp,
                l.saldo_afp,
                l.comentarios,
                l.estado_lead,
                l.created_at
            FROM tpi.leads l
            INNER JOIN tpi.personas p ON l.id_persona = p.id_persona
            LEFT JOIN tpi.catalogo_genero cg ON l.genero_id = cg.id
            LEFT JOIN tpi.catalogo_estado_civil cec ON l.estado_civil_id = cec.id
            LEFT JOIN tpi.catalogo_afp ca ON l.afp_id = ca.id
            {where_clause}
            ORDER BY {order_column} {direction}, l.created_at DESC, l.id_lead DESC
            LIMIT %s OFFSET %s
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query_count, where_params)
                total_row = cur.fetchone()
                total = total_row["total"] if total_row else 0

                cur.execute(query_data, [*where_params, limit, offset])
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
        query = "SELECT id, nombre FROM tpi.catalogo_afp WHERE activo = TRUE ORDER BY orden_visual, nombre"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    def get_active_genero() -> list[dict[str, Any]]:
        """Obtiene todos los gÃ©neros activos."""
        query = "SELECT id, nombre FROM tpi.catalogo_genero WHERE activo = TRUE ORDER BY orden_visual, nombre"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    def get_active_estado_civil() -> list[dict[str, Any]]:
        """Obtiene todos los estados civiles activos."""
        query = "SELECT id, nombre FROM tpi.catalogo_estado_civil WHERE activo = TRUE ORDER BY orden_visual, nombre"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    def get_crm_estado_lead_options() -> list[str]:
        """Return the actual lead states present in the model for CRM filtering."""
        query = """
            SELECT estado_lead
            FROM (
                SELECT DISTINCT LOWER(TRIM(l.estado_lead)) AS estado_lead
                FROM tpi.leads l
                WHERE COALESCE(NULLIF(TRIM(l.estado_lead), ''), '') <> ''
            ) estados
            ORDER BY
                CASE estado_lead
                    WHEN 'pendiente' THEN 1
                    WHEN 'aprobada' THEN 2
                    WHEN 'simulada' THEN 3
                    WHEN 'en gestion' THEN 4
                    WHEN 'cerrado' THEN 5
                    WHEN 'descartado' THEN 6
                    ELSE 99
                END,
                estado_lead
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                return [str(row["estado_lead"]) for row in rows if row.get("estado_lead")]
