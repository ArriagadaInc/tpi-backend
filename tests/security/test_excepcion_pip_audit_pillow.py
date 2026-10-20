"""Guarda la excepción ACOTADA de pip-audit para Pillow 12.3.0.

Contexto: Streamlit (todas las versiones hasta la 1.66.0) exige ``pillow<13`` y los avisos de Pillow
sólo se corrigen en 13.0.0, así que ``pip-audit`` ignora 8 avisos concretos (ver ``docs/SEGURIDAD.md``,
sección «Excepciones de pip-audit»). Esa excepción sólo es válida mientras la aplicación NO reciba
imágenes ni archivos de usuarios: los 8 avisos se explotan abriendo una imagen que manda un atacante.

Estas pruebas hacen que la suposición esté vigilada por el CI:

* los dos workflows ignoran exactamente las mismas 8 vulnerabilidades documentadas;
* la excepción está documentada en ``docs/SEGURIDAD.md``;
* mientras exista, no puede aparecer código que reciba archivos de usuarios (por ejemplo los adjuntos
  de comentarios del CRM): hay que subir a Pillow >= 13 y quitar la excepción ANTES;
* la excepción vence en la fecha escrita en los workflows: hay que revisarla y, si corresponde,
  extender la fecha con una justificación.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[2]
WORKFLOWS = (
    RAIZ / ".github" / "workflows" / "ci.yml",
    RAIZ / ".github" / "workflows" / "publish-dev-ecr-images.yml",
)
DOC = RAIZ / "docs" / "SEGURIDAD.md"

# Los 8 avisos de pillow 12.3.0 corregidos en 13.0.0 (alias GHSA en docs/SEGURIDAD.md).
EXCEPCIONES = frozenset(
    {
        "CVE-2026-112395",
        "CVE-2026-112397",
        "CVE-2026-112400",
        "CVE-2026-112404",
        "CVE-2026-112895",
        "CVE-2026-112896",
        "CVE-2026-112897",
        "CVE-2026-112899",
    }
)

# Código que recibe archivos de usuarios (en cualquiera de estas formas la excepción deja de ser válida).
PATRONES_PY = {
    r"\bUploadFile\b": "UploadFile de FastAPI",
    r"\bfile_uploader\b": "st.file_uploader de Streamlit",
    r"\bcamera_input\b": "st.camera_input de Streamlit",
    r"\brequest\.files\b": "request.files",
    r"\bImage\.open\(": "Image.open( de Pillow",
    r"^\s*(from|import)\s+PIL\b": "importación de PIL",
}
PATRONES_PLANTILLA = {
    r"type\s*=\s*[\"']file[\"']": 'input type="file"',
    r"multipart/form-data": "formulario multipart/form-data",
}

MENSAJE = (
    "La excepción de pip-audit para Pillow ya no es válida: {detalle}. Antes de aceptar archivos de "
    "usuarios hay que subir a Pillow >= 13 (tarea SEG-DESACOPLAR-STREAMLIT), quitar los --ignore-vuln "
    "de ci.yml y publish-dev-ecr-images.yml, y retirar esta prueba. Ver docs/SEGURIDAD.md."
)


def _comando_pip_audit(workflow: Path) -> str:
    datos = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    comandos = [
        str(paso["run"])
        for trabajo in datos["jobs"].values()
        for paso in trabajo.get("steps", [])
        if "pip-audit" in str(paso.get("run", ""))
    ]
    assert len(comandos) == 1, f"{workflow.name}: se esperaba exactamente un paso de pip-audit"
    return comandos[0]


def _ignoradas(workflow: Path) -> set[str]:
    return set(re.findall(r"--ignore-vuln\s+(\S+)", _comando_pip_audit(workflow)))


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_ignora_exactamente_las_excepciones_documentadas(workflow: Path) -> None:
    assert _ignoradas(workflow) == set(EXCEPCIONES)
    assert "--requirement requirements/runtime.lock" in _comando_pip_audit(workflow)


def test_ambos_workflows_ignoran_lo_mismo() -> None:
    assert _ignoradas(WORKFLOWS[0]) == _ignoradas(WORKFLOWS[1])


def test_la_excepcion_esta_documentada_en_seguridad() -> None:
    texto = DOC.read_text(encoding="utf-8")
    assert "Excepciones de pip-audit" in texto
    faltan = sorted(i for i in EXCEPCIONES if i not in texto)
    assert not faltan, f"docs/SEGURIDAD.md no documenta: {faltan}"


def test_el_runtime_lock_sigue_fijando_la_version_con_la_excepcion() -> None:
    """Si Pillow cambia de versión la excepción se revisa: los avisos son de 12.3.0."""
    lock = (RAIZ / "requirements" / "runtime.lock").read_text(encoding="utf-8")
    assert re.search(
        r"^pillow==12\.3\.0\s*$", lock, re.M
    ), "pillow cambió de versión: revisa y, si ya es >= 13, quita las excepciones de pip-audit."


def _fuentes_app() -> list[Path]:
    return [p for p in (RAIZ / "app").rglob("*.py") if "__pycache__" not in p.parts]


def test_la_aplicacion_no_recibe_archivos_de_usuarios_mientras_exista_la_excepcion() -> None:
    hallazgos: list[str] = []
    for ruta in _fuentes_app():
        texto = ruta.read_text(encoding="utf-8")
        for patron, nombre in PATRONES_PY.items():
            if re.search(patron, texto, re.M):
                hallazgos.append(f"{ruta.relative_to(RAIZ).as_posix()}: {nombre}")
    for ruta in (RAIZ / "app").rglob("*.html"):
        texto = ruta.read_text(encoding="utf-8")
        for patron, nombre in PATRONES_PLANTILLA.items():
            if re.search(patron, texto):
                hallazgos.append(f"{ruta.relative_to(RAIZ).as_posix()}: {nombre}")
    assert not hallazgos, MENSAJE.format(detalle="; ".join(sorted(hallazgos)))


def test_la_excepcion_no_esta_vencida() -> None:
    fechas = set()
    for workflow in WORKFLOWS:
        coincidencia = re.search(
            r"Vence:\s*(\d{4}-\d{2}-\d{2})", workflow.read_text(encoding="utf-8")
        )
        assert coincidencia, f"{workflow.name}: falta la línea «Vence: AAAA-MM-DD»"
        fechas.add(coincidencia.group(1))
    assert len(fechas) == 1, f"los workflows declaran vencimientos distintos: {sorted(fechas)}"
    vence = dt.date.fromisoformat(next(iter(fechas)))
    assert dt.date.today() <= vence, (
        f"La excepción de pip-audit para Pillow venció el {vence}. Revísala: si Pillow >= 13 ya es posible, "
        "quítala; si no, extiende la fecha en ambos workflows y en docs/SEGURIDAD.md con una justificación."
    )
