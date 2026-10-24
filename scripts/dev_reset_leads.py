"""Reinicio de los datos de DEV (AC-7 de CRM-ESTADOS-1-CATALOGO). Herramienta del HUMANO, nunca del Harness.

Borra TODOS los leads sinteticos de DEV (con sus personas, consentimientos, asignaciones, auditoria
de leads y los adjuntos del bucket) y siembra leads nuevos repartidos en los 12 estados del
catalogo, para probar filtros, cambio de estado, asignacion, conteos del dashboard y chips.

Seguridad:
  * Por defecto NO escribe nada (modo simulacion): muestra el destino, lo que borraria y lo que sembraria.
  * Con --ejecutar pide escribir la frase exacta REINICIAR DEV antes de tocar nada.
  * Solo corre por el tunel local a DEV (host local), con el usuario tpi_admin y la base `tpi`.
  * Si otra tabla referencia leads o personas, se detiene (no borra a ciegas).
  * Todo lo de la base va en UNA transaccion: si algo falla (incluido el borrado en S3), se revierte.
  * Los leads sembrados son ficticios: fuente_actual = 'seed_dev', correos @example.test.

Uso (desde la carpeta de tpi-backend, con el entorno del proyecto, el tunel a DEV abierto y las
variables DATABASE_* apuntando a DEV con tpi_admin; ver docs/database/08_DEV_DATA_INVENTORY.md):
  python scripts/dev_reset_leads.py --port 5433 --inspeccionar   # solo lectura: tablas dependientes
  python scripts/dev_reset_leads.py --port 5433                  # simulacion
  python scripts/dev_reset_leads.py --port 5433 --ejecutar       # pide confirmacion y reinicia
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, os.getcwd())

from psycopg import sql  # noqa: E402

from app.config import clear_settings_cache, get_settings  # noqa: E402
from app.database import close_pool, get_db_connection  # noqa: E402

FRASE = "REINICIAR DEV"
CUENTA_DEV = "821656895812"
BUCKET = "tpi-dev-adjuntos-821656895812-us-east-2"
PREFIJO_S3 = "leads/"
HOSTS_LOCALES = ("localhost", "127.0.0.1", "::1")
USUARIO_ADMIN = "tpi_admin"
BASE_DEV = "tpi"

# Estados del catalogo (docs/ui/referencia/estados/crm_states.py) y cuantos leads sembrar en cada uno.
REPARTO: tuple[tuple[str, int], ...] = (
    ("nuevo", 10),
    ("asignado", 6),
    ("sin_contacto", 4),
    ("en_seguimiento", 5),
    ("reunion_agendada", 3),
    ("reunion_realizada", 2),
    ("ficha_generada", 2),
    ("cerrado", 2),
    ("no_interesado", 2),
    ("datos_erroneos", 2),
    ("no_contactado", 2),
    ("perdido", 2),
)
# Estados que cuentan como cartera inactiva en el dashboard: no se siembran como estancados.
INACTIVOS = ("cerrado", "perdido")
# Cuantos leads activos (con asignacion) se siembran sin movimiento hace mas de 5 dias.
ESTANCADOS = 8

# Tablas que se sabe que referencian leads o personas (el script las limpia en este orden).
# Las cinco ultimas vienen del pipeline de datos (tpi-data-pipeline/setup_db.py, docs/BASE_DE_DATOS_TPI.md):
# todas con FK simple (sin ON DELETE) a leads, asi que hay que vaciarlas antes de borrar leads.
DEPENDIENTES_CONOCIDOS = {
    "tpi.api_idempotency",
    "tpi.consentimientos",
    "tpi.asignaciones",
    "tpi.auditoria",
    "tpi.leads",
    "tpi.personas",
    "tpi.campanas_atribucion",
    "tpi.citas",
    "tpi.eventos_lead",
    "tpi.fichas_diagnosticas",
    "tpi.ingesta_google_sheets",
}

NOMBRES = (
    "Camila",
    "Matias",
    "Valentina",
    "Benjamin",
    "Javiera",
    "Sebastian",
    "Constanza",
    "Nicolas",
    "Fernanda",
    "Cristobal",
    "Daniela",
    "Ignacio",
    "Antonia",
    "Joaquin",
    "Catalina",
    "Tomas",
    "Paula",
    "Felipe",
    "Macarena",
    "Diego",
    "Carolina",
    "Rodrigo",
    "Francisca",
    "Andres",
)
APELLIDOS = (
    "Soto",
    "Munoz",
    "Rojas",
    "Diaz",
    "Perez",
    "Silva",
    "Contreras",
    "Lopez",
    "Morales",
    "Araya",
    "Fuentes",
    "Espinoza",
    "Valenzuela",
    "Tapia",
    "Reyes",
    "Gutierrez",
    "Castillo",
    "Vargas",
)
AFPS = ("Capital", "Cuprum", "Habitat", "Modelo", "PlanVital", "ProVida", "Uno")
PRIORIDADES = ("alta", "media", "baja")
NOTAS = (
    "Se llamo al numero registrado, sin respuesta.",
    "Contesto, pidio que lo llamemos en la tarde.",
    "Quedo de enviar su ultima cartola de la AFP.",
    "Interesado en revisar opciones; se agenda llamada.",
    "Confirma que el saldo informado es correcto.",
)


# --------------------------------------------------------------------------------------
# Datos ficticios
# --------------------------------------------------------------------------------------
def dv_rut(numero: int) -> str:
    """Digito verificador (modulo 11) de un RUT chileno."""
    suma, factor = 0, 2
    for digito in reversed(str(numero)):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    return {11: "0", 10: "K"}.get(resto, str(resto))


def plan_de_leads(rng: random.Random, ahora: datetime) -> list[dict[str, Any]]:
    """Lista determinista (por semilla) de los leads a sembrar, sin tocar la base."""
    activos = [(e, i) for e, n in REPARTO if e != "nuevo" and e not in INACTIVOS for i in range(n)]
    estancados = set(rng.sample(activos, min(ESTANCADOS, len(activos))))
    ruts: set[int] = set()
    leads: list[dict[str, Any]] = []
    for estado, cantidad in REPARTO:
        for indice in range(cantidad):
            while True:
                numero = rng.randint(10_000_000, 24_999_999)
                if numero not in ruts:
                    ruts.add(numero)
                    break
            nombre = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)} {rng.choice(APELLIDOS)}"
            if (estado, indice) in estancados:
                dias_ingreso = rng.randint(9, 20)
            elif estado in INACTIVOS:
                dias_ingreso = rng.randint(6, 25)
            else:
                dias_ingreso = rng.randint(0, 4)
            ingreso = ahora - timedelta(days=dias_ingreso, hours=rng.randint(0, 20))
            asignacion = ingreso + timedelta(hours=rng.randint(1, 6))
            nacimiento = date(1960, 1, 1) + timedelta(days=rng.randint(0, 33 * 365))
            leads.append(
                {
                    "estado": estado,
                    "rut": f"{numero}-{dv_rut(numero)}",
                    "nombre": nombre,
                    "email": f"lead{numero}@example.test",
                    "telefono": f"+569555{rng.randint(10_000, 99_999)}",
                    "nacimiento": nacimiento,
                    "afp": rng.choice(AFPS),
                    "saldo": rng.randint(2_000_000, 60_000_000),
                    "prioridad": rng.choice(PRIORIDADES),
                    "ingreso": ingreso,
                    "asignacion": asignacion,
                    "notas": _notas(rng, estado, asignacion, ahora),
                }
            )
    return leads


def _notas(rng: random.Random, estado: str, desde: datetime, hasta: datetime) -> str | None:
    """Notas con el encabezado que escribe la app: '[dd/mm/YYYY HH:MM] Nombre' + texto."""
    if estado in ("nuevo", "asignado"):
        return None
    cantidad = rng.randint(1, 3)
    partes: list[str] = []
    momento = desde
    for _ in range(cantidad):
        momento = min(momento + timedelta(hours=rng.randint(2, 30)), hasta - timedelta(minutes=30))
        # La app escribe la hora de pared de America/Santiago; para datos ficticios basta UTC-3.
        local = (momento - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M")
        partes.append(f"[{local}] Equipo DEV\n{rng.choice(NOTAS)}")
    return "\n\n".join(partes)


# --------------------------------------------------------------------------------------
# AWS (CLI del humano; credenciales de su perfil)
# --------------------------------------------------------------------------------------
def aws(args: list[str], profile: str, region: str) -> Any:
    cmd = ["aws", *args, "--profile", profile, "--region", region, "--output", "json"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"aws {' '.join(args[:2])} fallo: {res.stderr.strip()[:400]}")
    return json.loads(res.stdout) if res.stdout.strip() else {}


def verificar_cuenta(profile: str, region: str) -> None:
    cuenta = aws(["sts", "get-caller-identity"], profile, region).get("Account")
    if cuenta != CUENTA_DEV:
        raise RuntimeError(f"La cuenta AWS es {cuenta} y se esperaba {CUENTA_DEV}.")


def listar_objetos(profile: str, region: str) -> list[str]:
    claves: list[str] = []
    token: str | None = None
    while True:
        args = ["s3api", "list-objects-v2", "--bucket", BUCKET, "--prefix", PREFIJO_S3]
        if token:
            args += ["--continuation-token", token]
        pagina = aws(args, profile, region)
        claves += [o["Key"] for o in pagina.get("Contents", [])]
        token = pagina.get("NextContinuationToken")
        if not token:
            return claves


def borrar_objetos(claves: list[str], profile: str, region: str) -> int:
    borrados = 0
    for i in range(0, len(claves), 1000):
        lote = claves[i : i + 1000]
        cuerpo = {"Objects": [{"Key": k} for k in lote], "Quiet": True}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(cuerpo, f)
            ruta = f.name
        try:
            resp = aws(
                ["s3api", "delete-objects", "--bucket", BUCKET, "--delete", "file://" + ruta],
                profile,
                region,
            )
        finally:
            Path(ruta).unlink(missing_ok=True)
        if resp.get("Errors"):
            raise RuntimeError(
                f"S3 no pudo borrar {len(resp['Errors'])} objetos: {resp['Errors'][:2]}"
            )
        borrados += len(lote)
    return borrados


# --------------------------------------------------------------------------------------
# Base de datos
# --------------------------------------------------------------------------------------
def cierre_dependientes(cur: Any) -> tuple[set[str], list[Any]]:
    """Tablas que dependen (directa o indirectamente) de leads/personas, y todas las FK del esquema."""
    cur.execute(SQL_FKS)
    fks = cur.fetchall()
    dependen = {"tpi.leads", "tpi.personas"}
    crecio = True
    while crecio:
        crecio = False
        for fk in fks:
            if fk["referencia"] in dependen and fk["tabla"] not in dependen:
                dependen.add(fk["tabla"])
                crecio = True
    return dependen, fks


def dependientes_inesperados(cur: Any) -> list[str]:
    """Tablas dependientes (incluso indirectas) que este script no sabe limpiar."""
    dependen, _ = cierre_dependientes(cur)
    return sorted(dependen - DEPENDIENTES_CONOCIDOS)


ACCION_FK = {"a": "NO ACTION", "r": "RESTRICT", "c": "CASCADE", "n": "SET NULL", "d": "SET DEFAULT"}

SQL_FKS = """
    SELECT cl.relnamespace::regnamespace::text || '.' || cl.relname AS tabla,
           rf.relnamespace::regnamespace::text || '.' || rf.relname AS referencia,
           (SELECT string_agg(a.attname, ',' ORDER BY k.ord)
              FROM unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord)
              JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum) AS columnas,
           c.confdeltype::text AS al_borrar
    FROM pg_constraint c
    JOIN pg_class cl ON cl.oid = c.conrelid
    JOIN pg_class rf ON rf.oid = c.confrelid
    WHERE c.contype = 'f' AND cl.relnamespace = 'tpi'::regnamespace
    ORDER BY 1, 3
"""


def inspeccionar(cur: Any) -> None:
    """Solo lectura: tablas que dependen (directa o indirectamente) de leads/personas."""
    dependen, fks = cierre_dependientes(cur)
    print("\nTablas que dependen de leads/personas (directa o indirectamente):")
    for tabla in sorted(dependen):
        esquema, nombre = tabla.split(".", 1)
        cur.execute(
            sql.SQL("SELECT count(*) AS n FROM {}.{}").format(
                sql.Identifier(esquema), sql.Identifier(nombre)
            )
        )
        print(f"  {tabla}: {cur.fetchone()['n']} filas")
        for fk in fks:
            if fk["tabla"] == tabla and fk["referencia"] in dependen:
                regla = ACCION_FK.get(fk["al_borrar"], fk["al_borrar"])
                print(f"      {fk['columnas']} -> {fk['referencia']}  (al borrar: {regla})")


def contar(cur: Any) -> dict[str, int]:
    consultas = {
        "leads": "SELECT count(*) AS n FROM tpi.leads",
        "personas": "SELECT count(*) AS n FROM tpi.personas",
        "consentimientos": "SELECT count(*) AS n FROM tpi.consentimientos",
        "asignaciones": "SELECT count(*) AS n FROM tpi.asignaciones",
        "auditoria de leads/personas": (
            "SELECT count(*) AS n FROM tpi.auditoria "
            "WHERE id_lead IS NOT NULL OR id_persona IS NOT NULL"
        ),
        "api_idempotency": "SELECT count(*) AS n FROM tpi.api_idempotency",
        "campanas_atribucion": "SELECT count(*) AS n FROM tpi.campanas_atribucion",
        "citas": "SELECT count(*) AS n FROM tpi.citas",
        "eventos_lead": "SELECT count(*) AS n FROM tpi.eventos_lead",
        "fichas_diagnosticas": "SELECT count(*) AS n FROM tpi.fichas_diagnosticas",
        "ingesta_google_sheets (ligadas a un lead)": (
            "SELECT count(*) AS n FROM tpi.ingesta_google_sheets WHERE id_lead_generado IS NOT NULL"
        ),
    }
    out: dict[str, int] = {}
    for nombre, consulta in consultas.items():
        cur.execute(consulta)
        out[nombre] = int(cur.fetchone()["n"])
    return out


def asesores_activos(cur: Any) -> list[str]:
    cur.execute("""
        SELECT id_asesor FROM tpi.asesores
        WHERE lower(btrim(rol)) = 'asesor' AND lower(btrim(estado_disponibilidad)) = 'activo'
        ORDER BY nombre
        """)
    return [str(f["id_asesor"]) for f in cur.fetchall()]


def borrar_todo(cur: Any) -> None:
    for sentencia in (
        "DELETE FROM tpi.api_idempotency",
        "DELETE FROM tpi.consentimientos",
        "DELETE FROM tpi.asignaciones",
        "DELETE FROM tpi.fichas_diagnosticas",
        "DELETE FROM tpi.citas",
        "DELETE FROM tpi.eventos_lead",
        "DELETE FROM tpi.campanas_atribucion",
        # Solo las filas ligadas a un lead; las de error de ingesta (sin lead) no se tocan.
        "DELETE FROM tpi.ingesta_google_sheets WHERE id_lead_generado IS NOT NULL",
        "DELETE FROM tpi.auditoria WHERE id_lead IS NOT NULL OR id_persona IS NOT NULL",
        "DELETE FROM tpi.leads",
        "DELETE FROM tpi.personas",
    ):
        cur.execute(sentencia)


def sembrar(cur: Any, leads: list[dict[str, Any]], asesores: list[str], rng: random.Random) -> None:
    for lead in leads:
        cur.execute(
            """
            INSERT INTO tpi.personas (rut, nombre_completo, email, telefono, fecha_nacimiento)
            VALUES (%s, %s, %s, %s, %s) RETURNING id_persona
            """,
            (lead["rut"], lead["nombre"], lead["email"], lead["telefono"], lead["nacimiento"]),
        )
        id_persona = cur.fetchone()["id_persona"]
        cur.execute(
            """
            INSERT INTO tpi.leads
                (id_persona, fecha_ingreso, afp_actual, saldo_afp, comentarios, estado_lead,
                 prioridad, origen_lead, fuente_actual, raw_payload, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'formulario_web', 'seed_dev', %s, %s, %s)
            RETURNING id_lead
            """,
            (
                id_persona,
                lead["ingreso"],
                lead["afp"],
                lead["saldo"],
                lead["notas"],
                lead["estado"],
                lead["prioridad"],
                json.dumps({"seed": "dev"}),
                lead["ingreso"],
                lead["ingreso"],
            ),
        )
        id_lead = cur.fetchone()["id_lead"]
        cur.execute(
            """
            INSERT INTO tpi.consentimientos
                (id_persona, id_lead, acepta_terminos, acepta_politica_privacidad,
                 fecha_aceptacion, version_terminos, version_politica, finalidad_contacto)
            VALUES (%s, %s, TRUE, TRUE, %s, 'seed-dev', 'seed-dev', TRUE)
            """,
            (id_persona, id_lead, lead["ingreso"]),
        )
        if lead["estado"] == "nuevo":
            continue
        id_asesor = rng.choice(asesores)
        cur.execute(
            """
            INSERT INTO tpi.asignaciones
                (id_lead, id_asesor, fecha_asignacion, asignado_por, regla_asignacion,
                 estado_asignacion)
            VALUES (%s, %s, %s, 'seed_dev', 'manual', 'activa')
            """,
            (id_lead, id_asesor, lead["asignacion"]),
        )
        cur.execute(
            """
            INSERT INTO tpi.auditoria
                (id_persona, id_lead, accion, tabla_afectada, fecha_hora, detalle)
            VALUES (%s, %s, 'asignacion_lead', 'tpi.asignaciones', %s, %s)
            """,
            (
                id_persona,
                id_lead,
                lead["asignacion"],
                json.dumps(
                    {
                        "actor_subject": "seed_dev",
                        "id_asesor": id_asesor,
                        "estado_anterior": "nuevo",
                        "estado_nuevo": "asignado",
                        "estado_asignacion": "activa",
                    }
                ),
            ),
        )


def resumen_final(cur: Any) -> list[tuple[str, int]]:
    cur.execute("SELECT estado_lead, count(*) AS n FROM tpi.leads GROUP BY 1 ORDER BY 2 DESC, 1")
    return [(f["estado_lead"], int(f["n"])) for f in cur.fetchall()]


# --------------------------------------------------------------------------------------
def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Reinicia los datos de DEV (simulacion por defecto).")
    p.add_argument("--port", type=int, default=None, help="Puerto de la base (tunel a DEV: 5433).")
    p.add_argument("--ejecutar", action="store_true", help="Aplica los cambios (pide la frase).")
    p.add_argument("--sin-s3", action="store_true", help="No toca el bucket de adjuntos.")
    p.add_argument(
        "--inspeccionar",
        action="store_true",
        help="Solo lectura: muestra las tablas que dependen de leads/personas y sus reglas de borrado.",
    )
    p.add_argument("--profile", default="tpi-dev", help="Perfil AWS (por defecto tpi-dev).")
    p.add_argument("--region", default="us-east-2")
    p.add_argument("--semilla", type=int, default=20261023, help="Semilla de los datos ficticios.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.port is not None:
        os.environ["DATABASE_PORT"] = str(args.port)
        clear_settings_cache()
    config = get_settings().database_config
    print(f"Destino: {config.safe_summary()}")
    problemas = []
    if config.host not in HOSTS_LOCALES:
        problemas.append("el host no es local: este script solo corre por el tunel a DEV")
    if config.user != USUARIO_ADMIN:
        problemas.append(f"el usuario debe ser {USUARIO_ADMIN} (es {config.user})")
    if config.database != BASE_DEV:
        problemas.append(f"la base debe ser '{BASE_DEV}' (es '{config.database}')")
    if problemas:
        print("DETENIDO: " + "; ".join(problemas) + ". No se toco nada.", file=sys.stderr)
        return 2

    ahora = datetime.now(UTC)
    rng = random.Random(args.semilla)
    leads = plan_de_leads(rng, ahora)

    try:
        claves: list[str] = []
        if not args.sin_s3 and not args.inspeccionar:
            verificar_cuenta(args.profile, args.region)
            claves = listar_objetos(args.profile, args.region)
        with get_db_connection(operation="reset_leads_dev") as conn:
            with conn.cursor() as cur:
                if args.inspeccionar:
                    inspeccionar(cur)
                    return 0
                extra = dependientes_inesperados(cur)
                if extra:
                    print(
                        f"DETENIDO: otras tablas referencian leads/personas: {extra}.",
                        file=sys.stderr,
                    )
                    print(
                        "Corre con --inspeccionar (solo lectura) para ver sus filas y reglas.",
                        file=sys.stderr,
                    )
                    return 2
                asesores = asesores_activos(cur)
                if not asesores:
                    print("DETENIDO: no hay asesores activos en tpi.asesores.", file=sys.stderr)
                    return 2
                antes = contar(cur)
                print("\nLo que se BORRARA:")
                for nombre, n in antes.items():
                    print(f"  {nombre}: {n}")
                print(
                    f"  objetos de adjuntos en S3 ({BUCKET}/{PREFIJO_S3}): "
                    f"{'(omitido: --sin-s3)' if args.sin_s3 else len(claves)}"
                )
                print(
                    f"\nLo que se SEMBRARA: {len(leads)} leads ficticios en "
                    f"{len(REPARTO)} estados; asesores activos disponibles: {len(asesores)}"
                )
                for estado, n in REPARTO:
                    print(f"  {estado}: {n}")
                if not args.ejecutar:
                    print("\nSimulacion: no se escribio nada. Agrega --ejecutar para aplicar.")
                    return 0
                if input(f"\nPara reiniciar DEV escribe exactamente: {FRASE}\n> ").strip() != FRASE:
                    print("La frase no coincide. No se toco nada.", file=sys.stderr)
                    return 2
                borrar_todo(cur)
                sembrar(cur, leads, asesores, rng)
                resultado = resumen_final(cur)
            if claves:
                borrados = borrar_objetos(claves, args.profile, args.region)
                print(f"S3: {borrados} objetos borrados.")
            conn.commit()
        print("\nListo. Leads sembrados por estado:")
        for estado, n in resultado:
            print(f"  {estado}: {n}")
        return 0
    except Exception as exc:
        print(
            f"ERROR: {exc}\nLa base se revirtio si el fallo fue antes del commit.", file=sys.stderr
        )
        return 1
    finally:
        close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
