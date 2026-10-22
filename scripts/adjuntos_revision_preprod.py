"""Medición de solo lectura del uso de adjuntos en notas (CRM-ADJUNTOS-REVISION-PREPROD).

Lee ``tpi.auditoria`` de una ventana de días (por defecto 30, configurable) y
muestra SOLO agregados: conteo por acción, rechazos por código, subidas con y sin
archivos incrustados, subidas por tipo, objetos y bytes subidos por mes (insumo
del costo de GuardDuty) y la cantidad de leads distintos con adjuntos y de
usuarios distintos que subieron.

Reglas de solo lectura (AC-3):

- Solo consultas ``SELECT`` parametrizadas; ningún ``INSERT``, ``UPDATE``,
  ``DELETE`` ni DDL.
- No imprime PII, textos de notas, nombres, SHA-256 ni identificadores de leads
  o personas (solo el conteo de leads y usuarios distintos).
- Usa la conexión de la aplicación (``get_db_connection``) sin credenciales
  nuevas ni escritura de claves.
- Si la conexión falla, sale con un mensaje claro y un código distinto de cero.

El Developer no tiene acceso a la base de datos de DEV ni a AWS: este script se
ejecuta desde la terminal del humano contra DEV por el túnel, con el entorno del
proyecto (``pip install -e .``) y las variables ``DATABASE_*`` apuntando a DEV. El túnel
SSM a DEV escucha en el puerto local 5433 (no en 5432): usa ``--port 5433`` o
``DATABASE_PORT=5433``.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Any

from app.config import clear_settings_cache, get_settings
from app.database import get_db_connection

TABLA_AFECTADA = "tpi.leads"
DIAS_POR_DEFECTO = 30
# El túnel SSM a la base de DEV escucha en el puerto local 5433 (el de RDS, al otro lado, es 5432).
PUERTO_TUNEL_DEV = 5433
PUERTO_POSTGRES = 5432
HOSTS_LOCALES = ("localhost", "127.0.0.1", "::1")

# Acciones de adjunto que escribe app/attachments/audit.py.
ACCIONES = (
    "adjunto_subido",
    "adjunto_rechazado",
    "adjunto_visto",
    "adjunto_descargado",
    "adjunto_eliminado",
)


@dataclass(frozen=True, slots=True)
class Metrica:
    """Una consulta agregada de solo lectura con su clave de salida."""

    clave: str
    titulo: str
    sql: str
    params: tuple[Any, ...]


def _ventana(days: int) -> tuple[Any, ...]:
    """Parámetros compartidos: tabla y ventana de días."""
    return (TABLA_AFECTADA, days)


def build_queries(days: int) -> list[Metrica]:
    """Devuelve las consultas agregadas, todas SELECT parametrizados y sin PII.

    ``days`` es el único valor del usuario y siempre se pasa como parámetro
    (``make_interval(days => %s)``); nunca se interpola en el SQL.
    """
    tabla, ventana = _ventana(days)
    acciones_sql = ", ".join(f"'{accion}'" for accion in ACCIONES)

    return [
        Metrica(
            clave="conteo_por_accion",
            titulo="Conteo por accion",
            sql=(
                "SELECT accion, COUNT(*) AS total "
                "FROM tpi.auditoria "
                "WHERE tabla_afectada = %s "
                f"AND accion IN ({acciones_sql}) "
                "AND fecha_hora >= now() - make_interval(days => %s) "
                "GROUP BY accion "
                "ORDER BY accion"
            ),
            params=(tabla, ventana),
        ),
        Metrica(
            clave="rechazos_por_codigo",
            titulo="Rechazos por codigo",
            sql=(
                "SELECT COALESCE(detalle->>'codigo_rechazo', '(sin codigo)') AS codigo, "
                "COUNT(*) AS total "
                "FROM tpi.auditoria "
                "WHERE tabla_afectada = %s "
                "AND accion = 'adjunto_rechazado' "
                "AND fecha_hora >= now() - make_interval(days => %s) "
                "GROUP BY 1 "
                "ORDER BY total DESC, codigo"
            ),
            params=(tabla, ventana),
        ),
        Metrica(
            clave="subidas_incrustados",
            titulo="Subidas con y sin archivos incrustados",
            sql=(
                "SELECT CASE "
                "WHEN COALESCE((detalle->>'archivos_incrustados')::boolean, false) "
                "THEN 'con_archivos_incrustados' ELSE 'sin_archivos_incrustados' END "
                "AS categoria, COUNT(*) AS total "
                "FROM tpi.auditoria "
                "WHERE tabla_afectada = %s "
                "AND accion = 'adjunto_subido' "
                "AND fecha_hora >= now() - make_interval(days => %s) "
                "GROUP BY 1 "
                "ORDER BY 1"
            ),
            params=(tabla, ventana),
        ),
        Metrica(
            clave="subidas_por_tipo",
            titulo="Subidas por tipo",
            sql=(
                "SELECT COALESCE(detalle->>'tipo', '(sin tipo)') AS tipo, COUNT(*) AS total "
                "FROM tpi.auditoria "
                "WHERE tabla_afectada = %s "
                "AND accion = 'adjunto_subido' "
                "AND fecha_hora >= now() - make_interval(days => %s) "
                "GROUP BY 1 "
                "ORDER BY total DESC, tipo"
            ),
            params=(tabla, ventana),
        ),
        Metrica(
            clave="objetos_bytes_por_mes",
            titulo="Objetos y bytes subidos por mes",
            sql=(
                "SELECT to_char(date_trunc('month', fecha_hora), 'YYYY-MM') AS mes, "
                "COUNT(*) AS objetos, "
                "COALESCE(SUM((detalle->>'tamano')::bigint), 0) AS bytes "
                "FROM tpi.auditoria "
                "WHERE tabla_afectada = %s "
                "AND accion = 'adjunto_subido' "
                "AND fecha_hora >= now() - make_interval(days => %s) "
                "GROUP BY 1 "
                "ORDER BY 1"
            ),
            params=(tabla, ventana),
        ),
        Metrica(
            clave="agregados_generales",
            titulo="Agregados generales",
            sql=(
                "SELECT COUNT(DISTINCT id_lead) AS leads_con_adjuntos, "
                "COUNT(DISTINCT (detalle->>'actor_subject')) AS usuarios_que_subieron "
                "FROM tpi.auditoria "
                "WHERE tabla_afectada = %s "
                "AND accion = 'adjunto_subido' "
                "AND fecha_hora >= now() - make_interval(days => %s)"
            ),
            params=(tabla, ventana),
        ),
    ]


def _format_bytes(value: Any) -> str:
    """Formatea bytes como número entero y MiB aproximado, sin exponer contenido."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 0
    mib = n / (1024 * 1024)
    return f"{n} bytes ({mib:.2f} MiB)"


def _rows_como_dict(rows: list[Any]) -> list[dict[str, Any]]:
    """Normaliza las filas a dict (la conexión real usa ``dict_row``)."""
    return [row for row in rows if isinstance(row, dict)]


def render(resultados: dict[str, list[Any]], days: int) -> str:
    """Renderiza los agregados en texto plano, sin PII ni identificadores."""
    lineas: list[str] = [
        "Adjuntos en notas - medicion de uso (solo lectura)",
        f"Ventana: {days} dias",
        "Fuente: tpi.auditoria (tabla_afectada = tpi.leads)",
        "",
    ]

    def bloque(titulo: str, filas: list[dict[str, Any]]) -> None:
        lineas.append(titulo)
        if not filas:
            lineas.append("  (sin eventos en la ventana)")
        for fila in filas:
            valores = "  ".join(f"{k}={v}" for k, v in fila.items())
            lineas.append(f"  {valores}")
        lineas.append("")

    conteo = _rows_como_dict(resultados.get("conteo_por_accion", []))
    bloque("Conteo por accion", conteo)

    rechazos = _rows_como_dict(resultados.get("rechazos_por_codigo", []))
    bloque("Rechazos por codigo", rechazos)

    incrustados = _rows_como_dict(resultados.get("subidas_incrustados", []))
    bloque("Subidas con y sin archivos incrustados", incrustados)

    tipos = _rows_como_dict(resultados.get("subidas_por_tipo", []))
    bloque("Subidas por tipo", tipos)

    lineas.append("Objetos y bytes subidos por mes")
    meses = _rows_como_dict(resultados.get("objetos_bytes_por_mes", []))
    if not meses:
        lineas.append("  (sin subidas en la ventana)")
    for fila in meses:
        lineas.append(
            f"  {fila.get('mes', '(sin mes)')}: {fila.get('objetos', 0)} objetos, "
            f"{_format_bytes(fila.get('bytes', 0))}"
        )
    lineas.append("")

    lineas.append("Agregados generales")
    generales = _rows_como_dict(resultados.get("agregados_generales", []))
    if not generales:
        lineas.append("  (sin subidas en la ventana)")
    for fila in generales:
        lineas.append(f"  leads distintos con adjuntos: {fila.get('leads_con_adjuntos', 0)}")
        lineas.append(f"  usuarios distintos que subieron: {fila.get('usuarios_que_subieron', 0)}")
    lineas.append("")

    return "\n".join(lineas).rstrip() + "\n"


def run_queries(conn: Any, queries: list[Metrica]) -> dict[str, list[Any]]:
    """Ejecuta cada consulta con su parámetro y devuelve los resultados por clave."""
    resultados: dict[str, list[Any]] = {}
    with conn.cursor() as cur:
        for metrica in queries:
            cur.execute(metrica.sql, metrica.params)
            resultados[metrica.clave] = cur.fetchall()
    return resultados


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mide el uso de adjuntos en notas (solo lectura, sin PII)."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DIAS_POR_DEFECTO,
        help=f"Ventana de días a medir (por defecto {DIAS_POR_DEFECTO}).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=(
            "Puerto de la base de datos; reemplaza DATABASE_PORT. Con el túnel SSM a DEV "
            f"es {PUERTO_TUNEL_DEV}. No aplica si usas DATABASE_URL (el puerto va en la URL)."
        ),
    )
    return parser.parse_args(argv)


def _destino() -> tuple[str, Any]:
    """Resumen sin secretos del destino de la conexión y su configuración (None si no es válida)."""
    try:
        config = get_settings().database_config
        return config.safe_summary(), config
    except Exception:  # una configuración inválida también se informa, sin ocultar el resto
        return "(la configuracion de la base de datos no es valida)", None


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    days = args.days
    if days < 1:
        print("Error: --days debe ser un entero mayor o igual a 1.", file=sys.stderr)
        return 2
    if args.port is not None:
        if not 1 <= args.port <= 65535:
            print("Error: --port debe estar entre 1 y 65535.", file=sys.stderr)
            return 2
        os.environ["DATABASE_PORT"] = str(args.port)
        clear_settings_cache()

    queries = build_queries(days)
    try:
        with get_db_connection(operation="adjuntos_revision_preprod") as conn:
            resultados = run_queries(conn, queries)
    except Exception as exc:  # el mensaje claro para el humano lo requiere
        destino, config = _destino()
        print(
            "No se pudo medir el uso de adjuntos: la conexion a la base de datos fallo. "
            "Verifica las variables DATABASE_* y el tunel a DEV.",
            file=sys.stderr,
        )
        print(f"Destino: {destino}", file=sys.stderr)
        if config is not None and config.port == PUERTO_POSTGRES and config.host in HOSTS_LOCALES:
            print(
                f"Pista: el tunel SSM a DEV escucha en el puerto local {PUERTO_TUNEL_DEV}, "
                f"no en {PUERTO_POSTGRES}. Usa --port {PUERTO_TUNEL_DEV} "
                f"(o DATABASE_PORT={PUERTO_TUNEL_DEV}).",
                file=sys.stderr,
            )
        print(f"Detalle: {exc}", file=sys.stderr)
        return 1

    print(render(resultados, days))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
