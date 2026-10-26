"""Usuarios de prueba del perfil Coordinador en DEV (AC-8 de CRM-PERFILES-1-RBAC). Herramienta del HUMANO.

Nunca la corre el Harness: el Harness no puede leer ni escribir AUTH_USERS_JSON. Todos los usuarios son
SINTETICOS de DEV: usuario coordinador.ejemploN, nombre «Coordinador Ejemplo N», clave igual al usuario.

Subcomandos (todos aceptan --secreto, --profile y --region; por defecto tpi/dev/auth-users, tpi-dev, us-east-2):
  listar    SOLO LECTURA. Usuarios del secreto: usuario, nombre, rol y si traen advisor_id. Nunca imprime hashes.
  asesores  Crea (idempotente) en tpi.asesores los asesores «Coordinador Ejemplo N», uno por coordinador, para que
            cada coordinador tenga su propia cartera. Necesita el tunel a DEV, tpi_admin y la base `tpi`.
  agregar   Agrega al secreto los usuarios coordinador.ejemploN (rol coordinator) con el advisor_id de su asesor.
            Conserva a todos los usuarios existentes y valida el resultado con el mismo parser que usa la app.
  quitar    Quita del secreto los usuarios coordinador.ejemplo* (para desmontar la prueba).

Seguridad:
  * Sin --ejecutar nunca escribe: muestra el plan. Con --ejecutar pide escribir una frase exacta.
  * Verifica la cuenta AWS (821656895812). Solo escribe una VERSION NUEVA del secreto: la anterior queda como
    AWSPREVIOUS para poder volver (aws secretsmanager update-secret-version-stage).
  * No imprime hashes, claves ni el JSON del secreto. El archivo temporal con la version nueva se borra al terminar.
  * `agregar` y `asesores` se niegan a correr contra una base que no sea tpi, con otro usuario que tpi_admin, o con un
    host que no sea local (tunel).

El rol coordinator solo lo entiende la version RBAC de la app: agregar los usuarios ANTES de desplegarla impide que la
version anterior arranque. Ejecuta `agregar` DESPUES del despliegue y reinicia el servidor de la aplicacion.

Uso (desde la carpeta del repo en la version desplegada, con el entorno del proyecto; ver docs/database/08_DEV_DATA_INVENTORY.md):
  python C:\\tc\\dev_usuarios.py listar
  python C:\\tc\\dev_usuarios.py asesores --port 5433 --ejecutar
  python C:\\tc\\dev_usuarios.py agregar --port 5433 --ejecutar
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, os.getcwd())

from argon2 import PasswordHasher  # noqa: E402

from app.auth.simple_dev import AuthConfigurationError, _parse_users  # noqa: E402
from app.config import clear_settings_cache, get_settings  # noqa: E402
from app.database import close_pool, get_db_connection  # noqa: E402

SECRETO = "tpi/dev/auth-users"
CUENTA_DEV = "821656895812"
PREFIJO_USUARIO = "coordinador.ejemplo"
PREFIJO_NOMBRE = "Coordinador Ejemplo"
ROL = "coordinator"
HOSTS_LOCALES = ("localhost", "127.0.0.1", "::1")
USUARIO_ADMIN = "tpi_admin"
BASE_DEV = "tpi"
FRASES = {
    "asesores": "CREAR ASESORES DEV",
    "agregar": "AGREGAR USUARIOS DEV",
    "quitar": "QUITAR USUARIOS DEV",
}


# --------------------------------------------------------------------------------------
# Datos de los coordinadores de prueba
# --------------------------------------------------------------------------------------
def coordinadores(cantidad: int) -> list[tuple[str, str]]:
    """[(usuario, nombre)] de los coordinadores de prueba: coordinador.ejemplo1.. y Coordinador Ejemplo 1.."""
    return [(f"{PREFIJO_USUARIO}{n}", f"{PREFIJO_NOMBRE} {n}") for n in range(1, cantidad + 1)]


def entrada_usuario(
    usuario: str, nombre: str, advisor_id: str, hasher: PasswordHasher
) -> dict[str, Any]:
    """Entrada de AUTH_USERS_JSON de un coordinador de prueba; la clave es igual al usuario (DEV, sintetico)."""
    return {
        "subject": f"dev-{usuario}",
        "username": usuario,
        "display_name": nombre,
        "role": ROL,
        "advisor_id": advisor_id,
        "password_hash": hasher.hash(usuario),
    }


# --------------------------------------------------------------------------------------
# Edicion del contenido del secreto (puro: sin AWS ni base de datos)
# --------------------------------------------------------------------------------------
def usuarios_de(payload: dict[str, Any]) -> list[dict[str, Any]]:
    users = payload.get("users")
    if not isinstance(users, list):
        raise ValueError("el secreto no tiene la forma {'users': [...]}")
    return users


def resumen_usuarios(payload: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """(usuario, nombre, rol, advisor_id presente) de cada usuario. Sin hashes."""
    filas = []
    for u in usuarios_de(payload):
        filas.append(
            (
                str(u.get("username", "?")),
                str(u.get("display_name", "?")),
                str(u.get("role", "?")),
                "si" if u.get("advisor_id") else "no",
            )
        )
    return filas


def agregar_usuarios(
    payload: dict[str, Any], nuevos: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Nuevo payload = el de antes + los usuarios que no existan; devuelve (payload, agregados, omitidos)."""
    existentes = {str(u.get("username", "")).casefold() for u in usuarios_de(payload)}
    agregados: list[str] = []
    omitidos: list[str] = []
    resultado = dict(payload)
    resultado["users"] = list(usuarios_de(payload))
    for nuevo in nuevos:
        if nuevo["username"].casefold() in existentes:
            omitidos.append(nuevo["username"])
            continue
        resultado["users"].append(nuevo)
        existentes.add(nuevo["username"].casefold())
        agregados.append(nuevo["username"])
    return resultado, agregados, omitidos


def quitar_usuarios(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Quita los usuarios cuyo nombre empieza por coordinador.ejemplo; devuelve (payload, quitados)."""
    quitados: list[str] = []
    conservados: list[dict[str, Any]] = []
    for u in usuarios_de(payload):
        if str(u.get("username", "")).casefold().startswith(PREFIJO_USUARIO):
            quitados.append(str(u["username"]))
        else:
            conservados.append(u)
    resultado = dict(payload)
    resultado["users"] = conservados
    return resultado, quitados


def serializar(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def validar(payload: dict[str, Any], esperados: list[str]) -> None:
    """Falla si la app no aceptaria el secreto, o si los usuarios esperados no entran con su clave."""
    try:
        usuarios = _parse_users(serializar(payload))
    except AuthConfigurationError as exc:
        raise ValueError(f"la app rechazaria el secreto: {exc}") from exc
    hasher = PasswordHasher()
    for usuario in esperados:
        configurado = usuarios.get(usuario.casefold())
        if configurado is None or configurado.user.role != ROL:
            raise ValueError(f"{usuario} no queda como {ROL} tras el parseo de la app")
        if configurado.user.advisor_id is None:
            raise ValueError(f"{usuario} quedo sin advisor_id valido (fallaria cerrado)")
        hasher.verify(configurado.password_hash, usuario)


# --------------------------------------------------------------------------------------
# AWS (CLI del humano)
# --------------------------------------------------------------------------------------
def aws(args: list[str], profile: str, region: str) -> Any:
    cmd = ["aws", *args, "--profile", profile, "--region", region, "--output", "json"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"aws {' '.join(args[:2])} fallo: {res.stderr.strip()[:300]}")
    return json.loads(res.stdout) if res.stdout.strip() else {}


def verificar_cuenta(profile: str, region: str) -> None:
    cuenta = aws(["sts", "get-caller-identity"], profile, region).get("Account")
    if cuenta != CUENTA_DEV:
        raise RuntimeError(f"La cuenta AWS es {cuenta} y se esperaba {CUENTA_DEV}.")


def leer_secreto(secreto: str, profile: str, region: str) -> dict[str, Any]:
    respuesta = aws(["secretsmanager", "get-secret-value", "--secret-id", secreto], profile, region)
    payload = json.loads(respuesta["SecretString"])
    usuarios_de(payload)
    return payload


def escribir_secreto(secreto: str, payload: dict[str, Any], profile: str, region: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(serializar(payload))
        ruta = f.name
    try:
        respuesta = aws(
            [
                "secretsmanager",
                "put-secret-value",
                "--secret-id",
                secreto,
                "--secret-string",
                "file://" + ruta,
            ],
            profile,
            region,
        )
    finally:
        Path(ruta).unlink(missing_ok=True)
    return str(respuesta.get("VersionId", "?"))


# --------------------------------------------------------------------------------------
# Base de datos (asesores de los coordinadores)
# --------------------------------------------------------------------------------------
def guardas_db(port: int | None) -> Any:
    """La configuracion de la base si el destino es DEV por el tunel; si no, lanza ValueError."""
    if port is not None:
        os.environ["DATABASE_PORT"] = str(port)
        clear_settings_cache()
    config = get_settings().database_config
    print(f"Destino: {config.safe_summary()}")
    problemas = []
    if config.host not in HOSTS_LOCALES:
        problemas.append("el host no es local: solo se llega a DEV por el tunel")
    if config.user != USUARIO_ADMIN:
        problemas.append(f"el usuario debe ser {USUARIO_ADMIN} (es {config.user})")
    if config.database != BASE_DEV:
        problemas.append(f"la base debe ser '{BASE_DEV}' (es '{config.database}')")
    if problemas:
        raise ValueError("; ".join(problemas))
    return config


def buscar_asesor(cur: Any, nombre: str) -> str | None:
    cur.execute(
        "SELECT id_asesor FROM tpi.asesores WHERE lower(btrim(nombre)) = lower(btrim(%s))",
        (nombre,),
    )
    filas = cur.fetchall()
    if len(filas) > 1:
        raise ValueError(f"hay mas de un asesor llamado {nombre!r}")
    return str(filas[0]["id_asesor"]) if filas else None


def crear_asesor(cur: Any, nombre: str) -> str:
    # rol y estado_disponibilidad se fijan explicitamente: el DDL versionado no declara defaults.
    cur.execute(
        """
        INSERT INTO tpi.asesores (nombre, rol, estado_disponibilidad, carga_activa)
        VALUES (%s, 'asesor', 'activo', 0) RETURNING id_asesor
        """,
        (nombre,),
    )
    return str(cur.fetchone()["id_asesor"])


def confirmar(subcomando: str, ejecutar: bool) -> bool:
    if not ejecutar:
        print("\nSimulacion: no se escribio nada. Agrega --ejecutar para aplicar.")
        return False
    frase = FRASES[subcomando]
    if input(f"\nPara continuar escribe exactamente: {frase}\n> ").strip() != frase:
        print("La frase no coincide. No se toco nada.", file=sys.stderr)
        return False
    return True


# --------------------------------------------------------------------------------------
def cmd_listar(args: argparse.Namespace) -> int:
    verificar_cuenta(args.profile, args.region)
    filas = resumen_usuarios(leer_secreto(args.secreto, args.profile, args.region))
    print(f"\nUsuarios en {args.secreto}: {len(filas)} (sin hashes)")
    print(f"  {'usuario':<28} {'nombre':<30} {'rol':<12} advisor_id")
    for usuario, nombre, rol, advisor in sorted(filas, key=lambda f: (f[2], f[0])):
        print(f"  {usuario:<28} {nombre:<30} {rol:<12} {advisor}")
    return 0


def cmd_asesores(args: argparse.Namespace) -> int:
    guardas_db(args.port)
    nombres = [nombre for _, nombre in coordinadores(args.cantidad)]
    with get_db_connection(operation="dev_usuarios_asesores") as conn:
        with conn.cursor() as cur:
            existentes = {n: buscar_asesor(cur, n) for n in nombres}
            print("\nAsesores de los coordinadores:")
            for nombre, id_asesor in existentes.items():
                print(f"  {nombre}: {'ya existe' if id_asesor else 'se creara'}")
            faltan = [n for n, i in existentes.items() if not i]
            if not faltan:
                print("\nNada que hacer: todos existen.")
                return 0
            if not confirmar("asesores", args.ejecutar):
                return 0
            for nombre in faltan:
                crear_asesor(cur, nombre)
        conn.commit()
    print(
        f"\nListo: {len(faltan)} asesor(es) creados. Siguiente: agregar (despues del despliegue)."
    )
    return 0


def cmd_agregar(args: argparse.Namespace) -> int:
    guardas_db(args.port)
    verificar_cuenta(args.profile, args.region)
    pedidos = coordinadores(args.cantidad)
    with get_db_connection(operation="dev_usuarios_agregar") as conn:
        with conn.cursor() as cur:
            ids = {nombre: buscar_asesor(cur, nombre) for _, nombre in pedidos}
    faltan = [n for n, i in ids.items() if not i]
    if faltan:
        print(
            f"DETENIDO: faltan asesores {faltan}. Corre primero: asesores --ejecutar.",
            file=sys.stderr,
        )
        return 2
    payload = leer_secreto(args.secreto, args.profile, args.region)
    hasher = PasswordHasher()
    nuevos = [entrada_usuario(u, n, str(ids[n]), hasher) for u, n in pedidos]
    actualizado, agregados, omitidos = agregar_usuarios(payload, nuevos)
    print(f"\nUsuarios hoy: {len(usuarios_de(payload))}")
    print(f"Se agregaran ({len(agregados)}): {', '.join(agregados) or '(ninguno)'}")
    print(f"Ya existian, se dejan igual ({len(omitidos)}): {', '.join(omitidos) or '(ninguno)'}")
    if not agregados:
        print("\nNada que hacer.")
        return 0
    validar(actualizado, agregados)
    print("Validacion con el parser de la app: OK (rol, advisor_id y clave de cada usuario nuevo).")
    if not confirmar("agregar", args.ejecutar):
        return 0
    version = escribir_secreto(args.secreto, actualizado, args.profile, args.region)
    print(
        f"\nListo: version nueva del secreto ({version[:8]}...); la anterior queda como AWSPREVIOUS."
    )
    print("Falta reiniciar el servidor de la aplicacion para que lo lea:")
    print(
        "  aws elasticbeanstalk restart-app-server --environment-name tpi-backoffice-dev-green "
        f"--profile {args.profile} --region {args.region}"
    )
    return 0


def cmd_quitar(args: argparse.Namespace) -> int:
    verificar_cuenta(args.profile, args.region)
    payload = leer_secreto(args.secreto, args.profile, args.region)
    actualizado, quitados = quitar_usuarios(payload)
    print(f"\nSe quitaran ({len(quitados)}): {', '.join(quitados) or '(ninguno)'}")
    if not quitados:
        print("\nNada que hacer.")
        return 0
    validar(actualizado, [])
    if not confirmar("quitar", args.ejecutar):
        return 0
    version = escribir_secreto(args.secreto, actualizado, args.profile, args.region)
    print(
        f"\nListo: version nueva del secreto ({version[:8]}...). Reinicia el servidor de la aplicacion."
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Usuarios Coordinador de prueba en DEV (humano).")
    sub = p.add_subparsers(dest="comando", required=True)
    for nombre, ayuda in (
        ("listar", "solo lectura"),
        ("asesores", "crea los asesores de los coordinadores"),
        ("agregar", "agrega los usuarios al secreto"),
        ("quitar", "quita los usuarios del secreto"),
    ):
        s = sub.add_parser(nombre, help=ayuda)
        s.add_argument("--secreto", default=SECRETO)
        s.add_argument("--profile", default="tpi-dev")
        s.add_argument("--region", default="us-east-2")
        s.add_argument(
            "--cantidad", type=int, default=2, help="cuantos coordinadores (por defecto 2)"
        )
        s.add_argument(
            "--port", type=int, default=None, help="puerto de la base (tunel a DEV: 5433)"
        )
        s.add_argument("--ejecutar", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not 1 <= args.cantidad <= 20:
        print("--cantidad debe estar entre 1 y 20.", file=sys.stderr)
        return 2
    comandos = {
        "listar": cmd_listar,
        "asesores": cmd_asesores,
        "agregar": cmd_agregar,
        "quitar": cmd_quitar,
    }
    try:
        return comandos[args.comando](args)
    except (ValueError, RuntimeError) as exc:
        print(f"DETENIDO: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
