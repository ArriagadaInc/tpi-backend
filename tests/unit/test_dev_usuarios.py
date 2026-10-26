"""Pruebas de ``scripts/dev_usuarios.py`` (usuarios Coordinador de prueba en DEV).

Sin AWS ni base de datos: ``aws`` y la conexion se simulan. Se prueba la edicion pura del secreto (agregar, quitar,
conservar a los existentes), la validacion con el parser real de la app, que nunca se impriman hashes y las
barreras (frase de confirmacion, cuenta AWS, destino de la base).
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from argon2 import PasswordHasher

from scripts import dev_usuarios as mod

HASHER = PasswordHasher()
ID_1 = "11111111-1111-4111-8111-111111111111"
ID_2 = "22222222-2222-4222-8222-222222222222"


def _secreto_base() -> dict[str, Any]:
    return {
        "users": [
            {
                "subject": "s1",
                "username": "asesor.desarrollo1",
                "display_name": "Asesor Desarrollo 1",
                "role": "advisor",
                "advisor_id": "33333333-3333-4333-8333-333333333333",
                "password_hash": HASHER.hash("x1"),
            },
            {
                "subject": "s2",
                "username": "alvaro.operaciones",
                "display_name": "Alvaro Operaciones",
                "role": "cto",
                "password_hash": HASHER.hash("x2"),
            },
        ]
    }


def _nuevos() -> list[dict[str, Any]]:
    return [
        mod.entrada_usuario("coordinador.ejemplo1", "Coordinador Ejemplo 1", ID_1, HASHER),
        mod.entrada_usuario("coordinador.ejemplo2", "Coordinador Ejemplo 2", ID_2, HASHER),
    ]


def test_los_coordinadores_de_prueba_se_nombran_por_numero() -> None:
    assert mod.coordinadores(2) == [
        ("coordinador.ejemplo1", "Coordinador Ejemplo 1"),
        ("coordinador.ejemplo2", "Coordinador Ejemplo 2"),
    ]


def test_la_entrada_trae_rol_coordinator_asesor_y_clave_igual_al_usuario() -> None:
    entrada = mod.entrada_usuario("coordinador.ejemplo1", "Coordinador Ejemplo 1", ID_1, HASHER)

    assert entrada["role"] == "coordinator"
    assert entrada["advisor_id"] == ID_1
    assert entrada["subject"] == "dev-coordinador.ejemplo1"
    assert HASHER.verify(entrada["password_hash"], "coordinador.ejemplo1")


def test_agregar_conserva_a_los_existentes_y_no_modifica_el_original() -> None:
    base = _secreto_base()
    copia = json.loads(json.dumps(base))

    nuevo, agregados, omitidos = mod.agregar_usuarios(base, _nuevos())

    assert base == copia
    assert agregados == ["coordinador.ejemplo1", "coordinador.ejemplo2"] and omitidos == []
    assert nuevo["users"][:2] == base["users"]
    assert len(nuevo["users"]) == 4


def test_agregar_es_idempotente_sin_distinguir_mayusculas() -> None:
    nuevo, _, _ = mod.agregar_usuarios(_secreto_base(), _nuevos())
    existente = dict(_nuevos()[0], username="Coordinador.Ejemplo1")

    again, agregados, omitidos = mod.agregar_usuarios(nuevo, [existente])

    assert agregados == [] and omitidos == ["Coordinador.Ejemplo1"]
    assert again["users"] == nuevo["users"]


def test_quitar_solo_elimina_los_coordinadores_de_prueba() -> None:
    con_nuevos, _, _ = mod.agregar_usuarios(_secreto_base(), _nuevos())

    restante, quitados = mod.quitar_usuarios(con_nuevos)

    assert quitados == ["coordinador.ejemplo1", "coordinador.ejemplo2"]
    assert [u["username"] for u in restante["users"]] == [
        "asesor.desarrollo1",
        "alvaro.operaciones",
    ]


def test_el_resumen_no_expone_hashes_ni_claves() -> None:
    filas = mod.resumen_usuarios(_secreto_base())
    texto = json.dumps(filas)

    assert ("asesor.desarrollo1", "Asesor Desarrollo 1", "advisor", "si") in filas
    assert ("alvaro.operaciones", "Alvaro Operaciones", "cto", "no") in filas
    assert "argon2" not in texto and "password" not in texto


def test_validar_acepta_el_secreto_con_los_coordinadores() -> None:
    nuevo, agregados, _ = mod.agregar_usuarios(_secreto_base(), _nuevos())

    mod.validar(nuevo, agregados)  # no lanza


def test_validar_rechaza_un_coordinador_sin_advisor_id() -> None:
    sin_asesor = _nuevos()
    del sin_asesor[0]["advisor_id"]
    nuevo, agregados, _ = mod.agregar_usuarios(_secreto_base(), sin_asesor)

    with pytest.raises(ValueError, match="advisor_id"):
        mod.validar(nuevo, agregados)


def test_validar_rechaza_un_rol_que_la_app_no_conoce() -> None:
    raro = _nuevos()
    raro[0]["role"] = "jefe"
    nuevo, agregados, _ = mod.agregar_usuarios(_secreto_base(), raro)

    with pytest.raises(ValueError, match="la app rechazaria"):
        mod.validar(nuevo, agregados)


def test_serializar_es_compacto_y_conserva_acentos() -> None:
    texto = mod.serializar({"users": [{"display_name": "Coordinación"}]})

    assert texto == '{"users":[{"display_name":"Coordinación"}]}'


class _AwsFalso:
    """Secreto en memoria: responde sts, get-secret-value y put-secret-value."""

    def __init__(self, payload: dict[str, Any], cuenta: str = mod.CUENTA_DEV) -> None:
        self.valor = json.dumps(payload)
        self.cuenta = cuenta
        self.escrituras = 0
        self.archivos: list[Path] = []

    def __call__(self, args: list[str], profile: str, region: str) -> dict[str, Any]:
        if args[:2] == ["sts", "get-caller-identity"]:
            return {"Account": self.cuenta}
        if args[:2] == ["secretsmanager", "get-secret-value"]:
            return {"SecretString": self.valor}
        if args[:2] == ["secretsmanager", "put-secret-value"]:
            ruta = Path(args[args.index("--secret-string") + 1].removeprefix("file://"))
            self.archivos.append(ruta)
            self.valor = ruta.read_text(encoding="utf-8")
            self.escrituras += 1
            return {"VersionId": "v2-abcdef123456"}
        raise AssertionError(f"llamada AWS inesperada: {args}")

    def usuarios(self) -> dict[str, dict[str, Any]]:
        return {u["username"]: u for u in json.loads(self.valor)["users"]}


class _CursorFalso:
    def __init__(self, asesores: dict[str, str]) -> None:
        self._asesores = asesores
        self._filas: list[dict[str, Any]] = []

    def execute(self, consulta: str, params: Any = None) -> None:
        nombre = str(params[0]).casefold()
        id_asesor = self._asesores.get(nombre)
        self._filas = [{"id_asesor": id_asesor}] if id_asesor else []

    def fetchall(self) -> list[dict[str, Any]]:
        return self._filas


def _conexion_falsa(asesores: dict[str, str]) -> Any:
    @contextmanager
    def conexion(operation: str = "") -> Iterator[Any]:
        class _Conn:
            @contextmanager
            def cursor(self) -> Iterator[_CursorFalso]:
                yield _CursorFalso(asesores)

            def commit(self) -> None:
                return None

        yield _Conn()

    return conexion


def _preparar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, aws_falso: _AwsFalso, asesores: dict[str, str]
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(mod, "aws", aws_falso)
    monkeypatch.setattr(mod, "guardas_db", lambda port: object())
    monkeypatch.setattr(mod, "get_db_connection", _conexion_falsa(asesores))
    monkeypatch.setattr(mod, "close_pool", lambda: None)


ASESORES = {"coordinador ejemplo 1": ID_1, "coordinador ejemplo 2": ID_2}


def test_listar_no_imprime_hashes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _preparar(monkeypatch, tmp_path, _AwsFalso(_secreto_base()), ASESORES)

    assert mod.main(["listar"]) == 0

    salida = capsys.readouterr().out
    assert "asesor.desarrollo1" in salida and "argon2" not in salida


def test_agregar_sin_ejecutar_no_escribe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    aws_falso = _AwsFalso(_secreto_base())
    _preparar(monkeypatch, tmp_path, aws_falso, ASESORES)

    assert mod.main(["agregar"]) == 0

    assert aws_falso.escrituras == 0
    assert "Simulacion" in capsys.readouterr().out


def test_agregar_con_frase_incorrecta_no_escribe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    aws_falso = _AwsFalso(_secreto_base())
    _preparar(monkeypatch, tmp_path, aws_falso, ASESORES)
    monkeypatch.setattr("builtins.input", lambda _="": "no")

    mod.main(["agregar", "--ejecutar"])

    assert aws_falso.escrituras == 0
    assert "La frase no coincide" in capsys.readouterr().err


def test_agregar_con_frase_correcta_escribe_una_version_y_borra_el_temporal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    aws_falso = _AwsFalso(_secreto_base())
    _preparar(monkeypatch, tmp_path, aws_falso, ASESORES)
    monkeypatch.setattr("builtins.input", lambda _="": mod.FRASES["agregar"])

    assert mod.main(["agregar", "--ejecutar"]) == 0

    usuarios = aws_falso.usuarios()
    assert aws_falso.escrituras == 1
    assert {"asesor.desarrollo1", "alvaro.operaciones"} <= set(usuarios)
    assert usuarios["coordinador.ejemplo1"]["advisor_id"] == ID_1
    assert usuarios["coordinador.ejemplo2"]["advisor_id"] == ID_2
    assert all(not ruta.exists() for ruta in aws_falso.archivos)
    salida = capsys.readouterr().out
    assert "restart-app-server" in salida and "argon2" not in salida


def test_agregar_se_detiene_si_faltan_los_asesores(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    aws_falso = _AwsFalso(_secreto_base())
    _preparar(monkeypatch, tmp_path, aws_falso, {"coordinador ejemplo 1": ID_1})

    assert mod.main(["agregar", "--ejecutar"]) == 2

    assert aws_falso.escrituras == 0
    assert "faltan asesores" in capsys.readouterr().err


def test_quitar_deja_a_los_demas_usuarios(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    con_nuevos, _, _ = mod.agregar_usuarios(_secreto_base(), _nuevos())
    aws_falso = _AwsFalso(con_nuevos)
    _preparar(monkeypatch, tmp_path, aws_falso, ASESORES)
    monkeypatch.setattr("builtins.input", lambda _="": mod.FRASES["quitar"])

    assert mod.main(["quitar", "--ejecutar"]) == 0

    assert set(aws_falso.usuarios()) == {"asesor.desarrollo1", "alvaro.operaciones"}


def test_se_niega_con_otra_cuenta_aws(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _preparar(monkeypatch, tmp_path, _AwsFalso(_secreto_base(), cuenta="000000000000"), ASESORES)

    assert mod.main(["listar"]) == 2

    assert "cuenta AWS" in capsys.readouterr().err


class _ConfigFalsa:
    def __init__(self, host: str, user: str, database: str) -> None:
        self.host, self.user, self.database = host, user, database

    def safe_summary(self) -> str:
        return f"{self.host}/{self.database} user={self.user}"


class _AjustesFalsos:
    def __init__(self, config: _ConfigFalsa) -> None:
        self.database_config = config


@pytest.mark.parametrize(
    ("host", "user", "database", "motivo"),
    [
        ("db.interno.example", "tpi_admin", "tpi", "el host no es local"),
        ("localhost", "tpi_app", "tpi", "el usuario debe ser tpi_admin"),
        ("localhost", "tpi_admin", "tpi_local", "la base debe ser 'tpi'"),
    ],
)
def test_la_base_solo_se_toca_por_el_tunel_a_dev(
    monkeypatch: pytest.MonkeyPatch, host: str, user: str, database: str, motivo: str
) -> None:
    monkeypatch.setattr(
        mod, "get_settings", lambda: _AjustesFalsos(_ConfigFalsa(host, user, database))
    )

    with pytest.raises(ValueError, match=motivo):
        mod.guardas_db(None)


# --------------------------------------------------------------------------------------
# CRM-AGENDA-1-MIGRACION: subcomandos `socios` y `marcar-coordinadores`
# --------------------------------------------------------------------------------------

ID_SOCIO = "55555555-5555-4555-8555-555555555555"


def _secreto_con_socios() -> dict[str, Any]:
    return {
        "users": [
            {
                "subject": "s-ceo",
                "username": "diego.operaciones",
                "display_name": "Diego",
                "role": "ceo",
                "password_hash": HASHER.hash("x"),
            },
            {
                "subject": "s-cto",
                "username": "alvaro.operaciones",
                "display_name": "Alvaro",
                "role": "cto",
                "password_hash": HASHER.hash("x"),
            },
            {
                "subject": "s1",
                "username": "asesor.desarrollo1",
                "display_name": "Asesor Desarrollo 1",
                "role": "advisor",
                "advisor_id": "33333333-3333-4333-8333-333333333333",
                "password_hash": HASHER.hash("x"),
            },
        ]
    }


class _EstadoAgenda:
    def __init__(self, asesores: dict[str, str], columna_agenda: bool = True) -> None:
        self.asesores = {k.casefold(): v for k, v in asesores.items()}
        self.roles: dict[str, str] = {}
        self.atiende: dict[str, bool] = {}
        self.columna_agenda = columna_agenda
        self._contador = 0

    def siguiente_id(self) -> str:
        self._contador += 1
        return f"99999999-9999-4999-8999-9999999999{self._contador:02d}"


class _CursorAgendaFalso:
    def __init__(self, estado: _EstadoAgenda) -> None:
        self._estado = estado
        self._filas: list[dict[str, Any]] = []

    def execute(self, consulta: str, params: Any = None) -> None:
        self._filas = []
        if "information_schema.columns" in consulta:
            self._filas = [{"existe": self._estado.columna_agenda}]
        elif "INSERT INTO tpi.asesores" in consulta:
            id_asesor = self._estado.siguiente_id()
            self._estado.asesores[str(params[0]).casefold()] = id_asesor
            self._estado.roles[id_asesor] = "socio"
            self._estado.atiende[id_asesor] = True
            self._filas = [{"id_asesor": id_asesor}]
        elif "UPDATE tpi.asesores" in consulta:
            id_asesor = str(params[0])
            if "rol = 'socio'" in consulta:
                self._estado.roles[id_asesor] = "socio"
            self._estado.atiende[id_asesor] = True
        else:
            nombre = str(params[0]).casefold()
            id_asesor = self._estado.asesores.get(nombre)
            self._filas = [{"id_asesor": id_asesor}] if id_asesor else []

    def fetchall(self) -> list[dict[str, Any]]:
        return self._filas

    def fetchone(self) -> dict[str, Any] | None:
        return self._filas[0] if self._filas else None


def _conexion_agenda_falsa(estado: _EstadoAgenda) -> Any:
    @contextmanager
    def conexion(operation: str = "") -> Iterator[Any]:
        class _Conn:
            @contextmanager
            def cursor(self) -> Iterator[_CursorAgendaFalso]:
                yield _CursorAgendaFalso(estado)

            def commit(self) -> None:
                return None

        yield _Conn()

    return conexion


def test_socios_del_secreto_extrae_ceo_y_cto() -> None:
    assert mod.socios_del_secreto(_secreto_con_socios()) == [
        ("diego.operaciones", "Diego"),
        ("alvaro.operaciones", "Alvaro"),
    ]


def test_coordinadores_del_secreto_extrae_coordinators_con_advisor_id() -> None:
    con_nuevos, _, _ = mod.agregar_usuarios(_secreto_base(), _nuevos())

    assert mod.coordinadores_del_secreto(con_nuevos) == [
        ("coordinador.ejemplo1", "Coordinador Ejemplo 1", ID_1),
        ("coordinador.ejemplo2", "Coordinador Ejemplo 2", ID_2),
    ]


def test_socios_sin_ejecutar_no_escribe_ni_imprime_hashes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    aws_falso = _AwsFalso(_secreto_con_socios())
    estado = _EstadoAgenda({})
    _preparar(monkeypatch, tmp_path, aws_falso, {})
    monkeypatch.setattr(mod, "get_db_connection", _conexion_agenda_falsa(estado))

    assert mod.main(["socios"]) == 0

    assert aws_falso.escrituras == 0
    assert estado.asesores == {}
    salida = capsys.readouterr().out
    assert "Simulacion" in salida and "Diego" in salida and "Alvaro" in salida
    assert "argon2" not in salida


def test_socios_con_frase_crea_socios(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    aws_falso = _AwsFalso(_secreto_con_socios())
    estado = _EstadoAgenda({})
    _preparar(monkeypatch, tmp_path, aws_falso, {})
    monkeypatch.setattr(mod, "get_db_connection", _conexion_agenda_falsa(estado))
    monkeypatch.setattr("builtins.input", lambda _="": mod.FRASES["socios"])

    assert mod.main(["socios", "--ejecutar"]) == 0

    assert set(estado.asesores) == {"diego", "alvaro"}
    assert all(estado.roles[i] == "socio" for i in estado.asesores.values())
    assert all(estado.atiende[i] is True for i in estado.asesores.values())


def test_socios_es_idempotente_y_no_duplica(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    aws_falso = _AwsFalso(_secreto_con_socios())
    estado = _EstadoAgenda({"Diego": ID_SOCIO})
    _preparar(monkeypatch, tmp_path, aws_falso, {})
    monkeypatch.setattr(mod, "get_db_connection", _conexion_agenda_falsa(estado))
    monkeypatch.setattr("builtins.input", lambda _="": mod.FRASES["socios"])

    assert mod.main(["socios", "--ejecutar"]) == 0

    # Diego ya existia: se marca sin duplicar; Alvaro se crea.
    assert estado.asesores["diego"] == ID_SOCIO
    assert estado.roles[ID_SOCIO] == "socio"
    assert estado.atiende[ID_SOCIO] is True
    assert "alvaro" in estado.asesores


def test_marcar_coordinadores_marca_por_advisor_id_sin_cambiar_rol(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    con_nuevos, _, _ = mod.agregar_usuarios(_secreto_base(), _nuevos())
    aws_falso = _AwsFalso(con_nuevos)
    estado = _EstadoAgenda({"coordinador ejemplo 1": ID_1, "coordinador ejemplo 2": ID_2})
    _preparar(monkeypatch, tmp_path, aws_falso, {})
    monkeypatch.setattr(mod, "get_db_connection", _conexion_agenda_falsa(estado))
    monkeypatch.setattr("builtins.input", lambda _="": mod.FRASES["marcar-coordinadores"])

    assert mod.main(["marcar-coordinadores", "--ejecutar"]) == 0

    assert estado.atiende.get(ID_1) is True
    assert estado.atiende.get(ID_2) is True
    # Los Coordinadores conservan rol 'asesor': no se toca el rol.
    assert estado.roles == {}


def test_socios_se_detiene_si_falta_la_columna_de_la_migracion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    aws_falso = _AwsFalso(_secreto_con_socios())
    estado = _EstadoAgenda({}, columna_agenda=False)
    _preparar(monkeypatch, tmp_path, aws_falso, {})
    monkeypatch.setattr(mod, "get_db_connection", _conexion_agenda_falsa(estado))

    assert mod.main(["socios", "--ejecutar"]) == 2

    assert "migracion 010" in capsys.readouterr().err


def test_marcar_coordinadores_se_detiene_si_falta_la_columna_de_la_migracion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    con_nuevos, _, _ = mod.agregar_usuarios(_secreto_base(), _nuevos())
    aws_falso = _AwsFalso(con_nuevos)
    estado = _EstadoAgenda({}, columna_agenda=False)
    _preparar(monkeypatch, tmp_path, aws_falso, {})
    monkeypatch.setattr(mod, "get_db_connection", _conexion_agenda_falsa(estado))

    assert mod.main(["marcar-coordinadores", "--ejecutar"]) == 2

    assert "migracion 010" in capsys.readouterr().err
