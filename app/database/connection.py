"""
Gestión de conexión a PostgreSQL.

Proporciona pool de conexiones, manejo de transacciones y contextos
para asegurar que las conexiones se cierren correctamente.
"""

from contextlib import contextmanager
from typing import Generator, Optional
import logging

import psycopg
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Pool global de conexiones
_connection_pool: Optional[ConnectionPool] = None


def initialize_pool() -> None:
    """
    Inicializar el pool de conexiones a PostgreSQL.
    
    Se debe llamar al inicio de la aplicación.
    """
    global _connection_pool
    
    if _connection_pool is not None:
        logger.warning("Pool de conexiones ya inicializado")
        return
    
    try:
        db_url = settings.get_database_url()
        _connection_pool = ConnectionPool(
            db_url,
            min_size=1,
            max_size=settings.database_pool_size,
            max_idle=settings.database_pool_timeout,
            open=False,  # Abierto manualmente
        )
        _connection_pool.open()
        logger.info("Pool de conexiones inicializado exitosamente")
    except Exception as e:
        logger.error(f"Error inicializando pool de conexiones: {e}")
        raise


def close_pool() -> None:
    """
    Cerrar el pool de conexiones.
    
    Se debe llamar al terminar la aplicación.
    """
    global _connection_pool
    
    if _connection_pool is None:
        return
    
    try:
        _connection_pool.close()
        _connection_pool = None
        logger.info("Pool de conexiones cerrado")
    except Exception as e:
        logger.error(f"Error cerrando pool: {e}")


def get_connection() -> psycopg.Connection:
    """
    Obtener una conexión del pool.

    Inicializa el pool automáticamente si aún no fue inicializado
    (necesario para Streamlit, que no llama a initialize_pool() al arrancar).
    
    Retorna:
        Conexión psycopg con row_factory = dict_row
    
    Raises:
        psycopg.OperationalError: Si no se puede conectar a la BD
    """
    global _connection_pool
    if _connection_pool is None:
        initialize_pool()
    
    conn = _connection_pool.getconn()
    conn.row_factory = dict_row
    return conn


def return_connection(conn: psycopg.Connection) -> None:
    """
    Devolver una conexión al pool.
    
    Args:
        conn: Conexión a devolver
    """
    if _connection_pool is None:
        if conn:
            conn.close()
        return
    
    _connection_pool.putconn(conn)


@contextmanager
def get_db_connection() -> Generator[psycopg.Connection, None, None]:
    """
    Context manager para obtener una conexión segura del pool.
    
    Uso:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM table")
                results = cur.fetchall()
    
    Yields:
        Conexión psycopg
    """
    conn = None
    try:
        conn = get_connection()
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error en contexto de BD: {e}")
        raise
    finally:
        if conn:
            # Cerrar cualquier transacción abierta (p.ej. tras un SELECT sin
            # commit explícito) antes de devolver la conexión al pool, para
            # evitar que quede "idle in transaction" y el pool tenga que
            # hacer rollback por su cuenta en cada checkin.
            try:
                if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
                    conn.rollback()
            except Exception:
                pass
            return_connection(conn)


def execute_query(
    query: str,
    params: Optional[tuple] = None,
    fetch_one: bool = False,
) -> Optional[dict]:
    """
    Ejecutar una consulta SELECT segura.
    
    Args:
        query: Consulta SQL (usar placeholders %s)
        params: Parámetros de la consulta
        fetch_one: Si True, retorna un registro. Si False, retorna lista.
    
    Returns:
        Un registro (dict) si fetch_one=True
        Una lista de registros (list[dict]) si fetch_one=False
    
    Raises:
        psycopg.Error: Si hay error en la BD
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            if fetch_one:
                return cur.fetchone()
            return cur.fetchall()


def execute_insert(
    query: str,
    params: Optional[tuple] = None,
    return_id: bool = False,
) -> Optional[dict]:
    """
    Ejecutar un INSERT y opcionalmente retornar el registro insertado.
    
    Args:
        query: INSERT query (preferentemente con RETURNING *)
        params: Parámetros
        return_id: Si True, espera que la query tenga RETURNING
    
    Returns:
        Registro insertado si RETURNING está en la query, None en otro caso
    
    Raises:
        psycopg.Error: Si hay error en la BD
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            if return_id:
                result = cur.fetchone()
            conn.commit()
            return result if return_id else None
