"""Reinicio de los datos de DEV (AC-7 de CRM-ESTADOS-1-CATALOGO). Herramienta del HUMANO, nunca del Harness.

Borra TODOS los leads sinteticos de DEV (con sus personas, consentimientos, asignaciones, auditoria
de leads, tablas del pipeline y los adjuntos del bucket) y siembra 100 leads nuevos repartidos en los
12 estados del catalogo, para probar filtros, cambio de estado, asignacion, conteos del dashboard y chips.

Cada lead se siembra COMPLETO, como lo deja la ingesta real del pipeline: persona (con sexo y estado
civil), lead (con las claves de los catalogos de genero, estado civil y AFP, saldo, prioridad, origen,
comentario inicial del formulario y su carga original), consentimiento (con IP y navegador), atribucion
de campana (UTM), evento de importacion y fila de ingesta. Hombres de 62 a 68 anios (centro 65) y
mujeres de 57 a 63 (centro 60), con nombres segun el sexo.

Seguridad:
  * Por defecto NO escribe nada (modo simulacion): muestra el destino, lo que borraria y lo que sembraria.
  * Con --ejecutar pide escribir la frase exacta REINICIAR DEV antes de tocar nada.
  * Solo corre por el tunel local a DEV (host local), con el usuario tpi_admin y la base `tpi`.
  * Si otra tabla referencia leads o personas, se detiene (no borra a ciegas).
  * Si falta un valor de los catalogos (genero, estado civil, AFP), se detiene antes de borrar.
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
import unicodedata
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
    ("nuevo", 24),
    ("asignado", 14),
    ("sin_contacto", 10),
    ("en_seguimiento", 12),
    ("reunion_agendada", 8),
    ("reunion_realizada", 5),
    ("ficha_generada", 5),
    ("cerrado", 5),
    ("no_interesado", 5),
    ("datos_erroneos", 4),
    ("no_contactado", 4),
    ("perdido", 4),
)
# Estados que cuentan como cartera inactiva en el dashboard: no se siembran como estancados.
INACTIVOS = ("cerrado", "perdido")
# Cuantos leads activos (con asignacion) se siembran sin movimiento hace mas de 5 dias.
ESTANCADOS = 20

# Edad de jubilacion en Chile: hombres 65 y mujeres 60. Los leads se siembran cerca de esa edad
# (centro y desviacion maxima en anios).
EDAD_CENTRO = {"M": 65, "F": 60}
EDAD_DESVIO = 3
SEXO_CODIGO = {"F": "FEMENINO", "M": "MASCULINO"}

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

# Catalogos que usan los leads (tpi-data-pipeline/catalogs.py) y los codigos que deben existir.
CATALOGOS = {
    "genero": "catalogo_genero",
    "estado_civil": "catalogo_estado_civil",
    "afp": "catalogo_afp",
}
CODIGOS_REQUERIDOS = {
    "genero": {"FEMENINO", "MASCULINO"},
    "estado_civil": {"SOLTERO", "CASADO", "DIVORCIADO", "VIUDO"},
    "afp": {"HABITAT", "CAPITAL", "CUPRUM", "MODELO", "PLANVITAL", "PROVIDA", "UNO"},
}

NOMBRES_F = (
    "María",
    "Rosa",
    "Ana",
    "Patricia",
    "Carmen",
    "Gloria",
    "Marta",
    "Sandra",
    "Verónica",
    "Claudia",
    "Marcela",
    "Ximena",
    "Soledad",
    "Cecilia",
    "Lorena",
    "Gabriela",
    "Elena",
    "Teresa",
    "Isabel",
    "Luisa",
    "Inés",
    "Nancy",
    "Silvia",
    "Alicia",
)
NOMBRES_M = (
    "Juan",
    "José",
    "Luis",
    "Carlos",
    "Jorge",
    "Manuel",
    "Pedro",
    "Héctor",
    "Raúl",
    "Sergio",
    "Hugo",
    "Eduardo",
    "Ricardo",
    "Mario",
    "Óscar",
    "Víctor",
    "Patricio",
    "Guillermo",
    "Alberto",
    "Fernando",
    "Rolando",
    "Gonzalo",
    "Miguel",
    "Francisco",
)
APELLIDOS = (
    "Soto",
    "Muñoz",
    "Rojas",
    "Díaz",
    "Pérez",
    "González",
    "Silva",
    "Contreras",
    "López",
    "Morales",
    "Araya",
    "Fuentes",
    "Espinoza",
    "Valenzuela",
    "Tapia",
    "Reyes",
    "Gutiérrez",
    "Castillo",
    "Vargas",
    "Sepúlveda",
    "Torres",
    "Ramírez",
    "Herrera",
    "Figueroa",
    "Carrasco",
    "Cortés",
    "Navarro",
    "Pizarro",
    "Vera",
    "Núñez",
)
# Estado civil: codigo del catalogo -> (texto para hombre, texto para mujer, peso).
ESTADOS_CIVILES = {
    "CASADO": ("Casado", "Casada", 45),
    "SOLTERO": ("Soltero", "Soltera", 20),
    "DIVORCIADO": ("Divorciado", "Divorciada", 20),
    "VIUDO": ("Viudo", "Viuda", 15),
}
AFPS = ("HABITAT", "CAPITAL", "CUPRUM", "MODELO", "PLANVITAL", "PROVIDA", "UNO")
PRIORIDADES = ("alta", "media", "baja")
PESOS_PRIORIDAD = (25, 45, 30)
COMENTARIOS_INICIALES = (
    "Quiero saber cuánto podría pensionarme.",
    "Estoy cerca de jubilar y quiero revisar mis opciones.",
    "Me interesa comparar renta vitalicia y retiro programado.",
    "Necesito orientación sobre mi AFP y mi saldo.",
    "Quisiera saber si me conviene esperar un tiempo más para pensionarme.",
    "Me recomendaron este servicio y quiero una asesoría.",
    "Tengo dudas sobre la reforma de pensiones y cómo me afecta.",
    "Quiero conocer cuánto recibiría mi familia si yo falto.",
)
# (utm_source, utm_medium, utm_campaign)
CAMPANAS = (
    ("google", "cpc", "retiro_programado_2026"),
    ("google", "cpc", "renta_vitalicia_2026"),
    ("facebook", "paid_social", "simulador_pension"),
    ("instagram", "paid_social", "reforma_pensiones"),
    ("newsletter", "email", "guia_jubilacion"),
    ("organico", "web", "seo_pension"),
)
UTM_TERMS = ("jubilacion anticipada", "pension minima", "renta vitalicia", "retiro programado")
UTM_CONTENTS = ("banner_a", "banner_b", "video_30s", "carrusel")
USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
)
# Rangos de IP reservados para documentacion (RFC 5737): nunca son de nadie real.
PREFIJOS_IP = ("192.0.2", "198.51.100", "203.0.113")
NOTAS = (
    "Se llamó al número registrado, sin respuesta.",
    "Contestó, pidió que lo llamemos en la tarde.",
    "Quedó de enviar su última cartola de la AFP.",
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


def edad_en(nacimiento: date, hoy: date) -> int:
    """Edad cumplida (anios calendario) de `nacimiento` al dia `hoy`."""
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


def _hace_anios(hoy: date, anios: int) -> date:
    try:
        return hoy.replace(year=hoy.year - anios)
    except ValueError:  # 29 de febrero
        return hoy.replace(year=hoy.year - anios, day=28)


def _sin_tildes(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in base if not unicodedata.combining(c)).lower()


def plan_de_leads(rng: random.Random, ahora: datetime) -> list[dict[str, Any]]:
    """Lista determinista (por semilla) de los leads a sembrar, sin tocar la base."""
    total = sum(cantidad for _, cantidad in REPARTO)
    sexos = ["F", "M"] * (total // 2 + 1)
    rng.shuffle(sexos)
    activos = [(e, i) for e, n in REPARTO if e != "nuevo" and e not in INACTIVOS for i in range(n)]
    estancados = set(rng.sample(activos, min(ESTANCADOS, len(activos))))
    ruts: set[int] = set()
    leads: list[dict[str, Any]] = []
    for estado, cantidad in REPARTO:
        for indice in range(cantidad):
            sexo = sexos[len(leads)]
            # Los RUT de personas nacidas hacia 1957-1969 rondan los 5,5 a 12,5 millones.
            while True:
                numero = rng.randint(5_500_000, 12_500_000)
                if numero not in ruts:
                    ruts.add(numero)
                    break
            nombre_pila = rng.choice(NOMBRES_F if sexo == "F" else NOMBRES_M)
            apellido1, apellido2 = rng.choice(APELLIDOS), rng.choice(APELLIDOS)
            if (estado, indice) in estancados:
                dias_ingreso = rng.randint(9, 20)
            elif estado in INACTIVOS:
                dias_ingreso = rng.randint(6, 25)
            else:
                dias_ingreso = rng.randint(0, 4)
            ingreso = ahora - timedelta(days=dias_ingreso, hours=rng.randint(0, 20))
            asignacion = ingreso + timedelta(hours=rng.randint(1, 6))
            centro = EDAD_CENTRO[sexo]
            edad = round(rng.triangular(centro - EDAD_DESVIO, centro + EDAD_DESVIO, centro))
            nacimiento = _hace_anios(ahora.date(), edad) - timedelta(days=rng.randint(0, 364))
            civil = rng.choices(
                list(ESTADOS_CIVILES), weights=[v[2] for v in ESTADOS_CIVILES.values()]
            )[0]
            civil_texto = ESTADOS_CIVILES[civil][1 if sexo == "F" else 0]
            campana, termino, contenido = (
                rng.choice(CAMPANAS),
                rng.choice(UTM_TERMS),
                rng.choice(UTM_CONTENTS),
            )
            comentario = rng.choice(COMENTARIOS_INICIALES)
            notas = _notas(rng, estado, asignacion, ahora)
            leads.append(
                {
                    "estado": estado,
                    "sexo": sexo,
                    "rut": f"{numero}-{dv_rut(numero)}",
                    "nombre_pila": nombre_pila,
                    "nombre": f"{nombre_pila} {apellido1} {apellido2}",
                    "email": f"{_sin_tildes(nombre_pila)}.{_sin_tildes(apellido1)}{numero}@example.test",
                    "telefono": f"+569555{rng.randint(10_000, 99_999)}",
                    "nacimiento": nacimiento,
                    "estado_civil": civil,
                    "estado_civil_texto": civil_texto,
                    "afp": rng.choice(AFPS),
                    "saldo": rng.randint(20_000, 160_000) * 1000,
                    "prioridad": rng.choices(PRIORIDADES, weights=PESOS_PRIORIDAD)[0],
                    "ingreso": ingreso,
                    "asignacion": asignacion,
                    "comentario_inicial": comentario,
                    "comentarios": comentario if notas is None else f"{comentario}\n\n{notas}",
                    "utm": {
                        "utm_source": campana[0],
                        "utm_medium": campana[1],
                        "utm_campaign": campana[2],
                        "utm_term": termino,
                        "utm_content": contenido,
                    },
                    "ip": f"{rng.choice(PREFIJOS_IP)}.{rng.randint(1, 254)}",
                    "user_agent": rng.choice(USER_AGENTS),
                    "fila": len(leads) + 2,
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


def resumen_del_plan(leads: list[dict[str, Any]], hoy: date) -> list[str]:
    """Lineas de la simulacion: sexo, edades y estado civil de lo que se sembraria."""
    lineas = []
    for sexo, etiqueta in (("M", "Hombres"), ("F", "Mujeres")):
        edades = [edad_en(lead["nacimiento"], hoy) for lead in leads if lead["sexo"] == sexo]
        lineas.append(
            f"  {etiqueta}: {len(edades)} (edad {min(edades)} a {max(edades)}, "
            f"promedio {sum(edades) / len(edades):.1f})"
        )
    return lineas


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


class CatalogoIncompletoError(RuntimeError):
    """Falta un valor de los catalogos que los leads sembrados necesitan."""


def cargar_catalogos(cur: Any) -> dict[str, dict[str, tuple[Any, str]]]:
    """Catalogos activos: {clave: {codigo: (id, nombre)}}. Falla si falta algun codigo requerido."""
    catalogos: dict[str, dict[str, tuple[Any, str]]] = {}
    faltan: list[str] = []
    for clave, tabla in CATALOGOS.items():
        cur.execute(
            sql.SQL("SELECT id, codigo, nombre FROM {} WHERE activo").format(
                sql.Identifier("tpi", tabla)
            )
        )
        catalogos[clave] = {f["codigo"]: (f["id"], f["nombre"]) for f in cur.fetchall()}
        for codigo in sorted(CODIGOS_REQUERIDOS[clave] - set(catalogos[clave])):
            faltan.append(f"{tabla}.{codigo}")
    if faltan:
        raise CatalogoIncompletoError(
            "faltan valores activos en los catalogos: " + ", ".join(faltan) + ". No se toco nada."
        )
    return catalogos


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


def formulario_de(lead: dict[str, Any], genero: str, afp: str) -> dict[str, str]:
    """Fila original del formulario (con las columnas de la hoja de Google Sheets)."""
    return {
        "NOMBRE": lead["nombre"],
        "RUT": lead["rut"],
        "EMAIL": lead["email"],
        "TELEFONO": lead["telefono"],
        "FECHA NACIMIENTO": lead["nacimiento"].isoformat(),
        "GENERO": genero,
        "ESTADO CIVIL": lead["estado_civil_texto"],
        "AFP": afp,
        "SALDO AFP": str(lead["saldo"]),
        "COMENTARIOS": lead["comentario_inicial"],
        "CONSENTIMIENTO": "Si",
        "UTM SOURCE": lead["utm"]["utm_source"],
        "UTM MEDIUM": lead["utm"]["utm_medium"],
        "UTM CAMPAIGN": lead["utm"]["utm_campaign"],
        "UTM TERM": lead["utm"]["utm_term"],
        "UTM CONTENT": lead["utm"]["utm_content"],
    }


def sembrar(
    cur: Any,
    leads: list[dict[str, Any]],
    asesores: list[str],
    catalogos: dict[str, dict[str, tuple[Any, str]]],
    rng: random.Random,
) -> None:
    for lead in leads:
        genero_id, genero_nombre = catalogos["genero"][SEXO_CODIGO[lead["sexo"]]]
        civil_id, _ = catalogos["estado_civil"][lead["estado_civil"]]
        afp_id, afp_nombre = catalogos["afp"][lead["afp"]]
        formulario = formulario_de(lead, genero_nombre, afp_nombre)
        cur.execute(
            """
            INSERT INTO tpi.personas
                (rut, nombre_completo, email, telefono, fecha_nacimiento, genero, estado_civil)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id_persona
            """,
            (
                lead["rut"],
                lead["nombre"],
                lead["email"],
                lead["telefono"],
                lead["nacimiento"],
                genero_nombre,
                lead["estado_civil_texto"],
            ),
        )
        id_persona = cur.fetchone()["id_persona"]
        cur.execute(
            """
            INSERT INTO tpi.leads
                (id_persona, fecha_ingreso, afp_actual, afp_id, genero_id, estado_civil_id,
                 saldo_afp, comentarios, estado_lead, prioridad, origen_lead, fuente_actual,
                 raw_payload, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'formulario_web', 'seed_dev',
                    %s, %s, %s)
            RETURNING id_lead
            """,
            (
                id_persona,
                lead["ingreso"],
                afp_nombre,
                afp_id,
                genero_id,
                civil_id,
                lead["saldo"],
                lead["comentarios"],
                lead["estado"],
                lead["prioridad"],
                json.dumps({"seed": "dev", "formulario": formulario}, ensure_ascii=False),
                lead["ingreso"],
                lead["ingreso"],
            ),
        )
        id_lead = cur.fetchone()["id_lead"]
        cur.execute(
            """
            INSERT INTO tpi.ingesta_google_sheets
                (fila_origen, sheet_origen, payload_original, estado_procesamiento,
                 errores_validacion, id_lead_generado, fecha_ingesta)
            VALUES (%s, 'seed_dev', %s, 'procesado', '[]'::jsonb, %s, %s)
            RETURNING id_ingesta
            """,
            (
                lead["fila"],
                json.dumps(formulario, ensure_ascii=False),
                id_lead,
                lead["ingreso"],
            ),
        )
        id_ingesta = cur.fetchone()["id_ingesta"]
        cur.execute(
            """
            INSERT INTO tpi.consentimientos
                (id_persona, id_lead, acepta_terminos, acepta_politica_privacidad,
                 fecha_aceptacion, version_terminos, version_politica, ip_origen, user_agent,
                 finalidad_contacto)
            VALUES (%s, %s, TRUE, TRUE, %s, 'v1.0', 'v1.0', %s, %s, TRUE)
            """,
            (id_persona, id_lead, lead["ingreso"], lead["ip"], lead["user_agent"]),
        )
        cur.execute(
            """
            INSERT INTO tpi.campanas_atribucion
                (id_lead, utm_source, utm_medium, utm_campaign, utm_term, utm_content)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                id_lead,
                lead["utm"]["utm_source"],
                lead["utm"]["utm_medium"],
                lead["utm"]["utm_campaign"],
                lead["utm"]["utm_term"],
                lead["utm"]["utm_content"],
            ),
        )
        cur.execute(
            """
            INSERT INTO tpi.eventos_lead
                (id_lead, tipo_evento, descripcion, fecha_evento, usuario_responsable, metadata)
            VALUES (%s, 'lead_importado_sheets', 'Lead sintetico sembrado en DEV (seed_dev).',
                    %s, 'seed_dev', %s)
            """,
            (
                id_lead,
                lead["ingreso"],
                json.dumps(
                    {
                        "id_ingesta": str(id_ingesta),
                        "fila_origen": lead["fila"],
                        "sheet_origen": "seed_dev",
                        "catalogos": {
                            "genero_id": str(genero_id),
                            "estado_civil_id": str(civil_id),
                            "afp_id": str(afp_id),
                        },
                    }
                ),
            ),
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


def resumen_final(cur: Any) -> tuple[list[tuple[str, int]], list[tuple[str, int, int, int, int]]]:
    """Leads por estado y, por sexo, cantidad y edades (minima, maxima y promedio)."""
    cur.execute("SELECT estado_lead, count(*) AS n FROM tpi.leads GROUP BY 1 ORDER BY 2 DESC, 1")
    estados = [(f["estado_lead"], int(f["n"])) for f in cur.fetchall()]
    cur.execute("""
        SELECT genero, count(*) AS n, min(edad)::int AS minimo, max(edad)::int AS maximo,
               round(avg(edad))::int AS promedio
        FROM (
            SELECT p.genero, date_part('year', age(CURRENT_DATE, p.fecha_nacimiento)) AS edad
            FROM tpi.leads l JOIN tpi.personas p ON p.id_persona = l.id_persona
        ) t
        GROUP BY genero ORDER BY genero
        """)
    sexos = [
        (f["genero"], int(f["n"]), int(f["minimo"]), int(f["maximo"]), int(f["promedio"]))
        for f in cur.fetchall()
    ]
    return estados, sexos


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
                try:
                    catalogos = cargar_catalogos(cur)
                except CatalogoIncompletoError as exc:
                    print(f"DETENIDO: {exc}", file=sys.stderr)
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
                    f"\nLo que se SEMBRARA: {len(leads)} leads ficticios completos en "
                    f"{len(REPARTO)} estados; asesores activos disponibles: {len(asesores)}"
                )
                for estado, n in REPARTO:
                    print(f"  {estado}: {n}")
                for linea in resumen_del_plan(leads, ahora.date()):
                    print(linea)
                if not args.ejecutar:
                    print("\nSimulacion: no se escribio nada. Agrega --ejecutar para aplicar.")
                    return 0
                if input(f"\nPara reiniciar DEV escribe exactamente: {FRASE}\n> ").strip() != FRASE:
                    print("La frase no coincide. No se toco nada.", file=sys.stderr)
                    return 2
                borrar_todo(cur)
                sembrar(cur, leads, asesores, catalogos, rng)
                estados, sexos = resumen_final(cur)
            if claves:
                borrados = borrar_objetos(claves, args.profile, args.region)
                print(f"S3: {borrados} objetos borrados.")
            conn.commit()
        print("\nListo. Leads sembrados por estado:")
        for estado, n in estados:
            print(f"  {estado}: {n}")
        print("Por sexo (edad minima / maxima / promedio):")
        for genero, n, minimo, maximo, promedio in sexos:
            print(f"  {genero}: {n} ({minimo} / {maximo} / {promedio})")
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
