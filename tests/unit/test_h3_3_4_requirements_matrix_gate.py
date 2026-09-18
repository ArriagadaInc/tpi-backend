"""Gate programático de trazabilidad de la matriz H3.3.4.

Impide que vuelva a ocurrir el defecto F1 de ``evidence/H3.3.4/reviewer/review-01.json``:
la columna de prueba automatizada citaba archivos de test planificados/inexistentes.

El gate es deliberadamente estricto sobre qué cuenta como ruta de prueba: solo reconoce
referencias con la forma ``tests/<unit|integration|security|e2e>/<archivo>.py`` (y, si se
cita, ``::test_<nombre>``). Cualquier texto narrativo, ruta de aplicación
(``app/...``), script (``scripts/...``) o evidencia futura (``evidence/...``) queda fuera
del alcance del gate y no se interpreta como ruta de prueba.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX = REPO_ROOT / "docs" / "H3_3_4_REQUIREMENTS_MATRIX.md"

# Solo paths bajo tests/ con directorio de nivel 2 explícito (unit/integration/security/e2e).
_TEST_PATH_RE = re.compile(r"tests/(?:unit|integration|security|e2e)/[\w-]+\.py(?:::[A-Za-z_]\w*)?")
_REQ_ID_RE = re.compile(r"\bREQ-[A-Z]+-\d{2}\b")
_AC_ID_RE = re.compile(r"\bAC-\d{1,2}\b")

_EXPECTED_REQ_IDS = {
    *(f"REQ-A-{i:02d}" for i in range(1, 25)),
    *(f"REQ-B-{i:02d}" for i in range(1, 31)),
    *(f"REQ-S-{i:02d}" for i in range(1, 14)),
}


def _matrix_text() -> str:
    assert MATRIX.exists(), f"no existe la matriz de trazabilidad: {MATRIX}"
    return MATRIX.read_text(encoding="utf-8")


def _test_refs(text: str) -> list[tuple[str, str | None]]:
    """Return [(file_path_relative_to_repo, test_name_or_None), ...] for cited tests."""
    refs: list[tuple[str, str | None]] = []
    for match in _TEST_PATH_RE.finditer(text):
        token = match.group(0)
        if "::" in token:
            path_part, name = token.split("::", 1)
        else:
            path_part, name = token, None
        refs.append((path_part, name))
    return refs


def test_all_cited_test_paths_exist() -> None:
    text = _matrix_text()
    refs = _test_refs(text)
    assert refs, "la matriz no cita ninguna prueba automatizada; gate sin cobertura"
    missing = sorted({path for path, _ in refs if not (REPO_ROOT / path).exists()})
    assert (
        not missing
    ), "rutas de prueba citadas en la matriz que no existen en el repositorio: " + ", ".join(
        missing
    )


def test_all_cited_test_names_resolve() -> None:
    text = _matrix_text()
    refs = _test_refs(text)
    unresolved: list[str] = []
    for path, name in refs:
        if name is None:
            continue
        source = (REPO_ROOT / path).read_text(encoding="utf-8")
        if not re.search(rf"^\s*def\s+{re.escape(name)}\s*\(", source, re.MULTILINE):
            unresolved.append(f"{path}::{name}")
    assert (
        not unresolved
    ), "nombres de test citados en la matriz que no existen como función: " + ", ".join(
        sorted(unresolved)
    )


def test_no_reference_to_follow_up_task_h3_3_5() -> None:
    text = _matrix_text()
    assert "H3.3.5" not in text, "la matriz referencia una tarea posterior H3.3.5"


def test_acceptance_criteria_1_to_18_present() -> None:
    text = _matrix_text()
    acs = set(_AC_ID_RE.findall(text))
    missing = [f"AC-{i}" for i in range(1, 19) if f"AC-{i}" not in acs]
    assert not missing, "AC faltantes en la matriz: " + ", ".join(missing)


def _requirement_definition_ids(text: str) -> list[str]:
    """IDs de la columna REQ de las tablas de definición (§3/§4/§5)."""
    ids: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("| REQ-"):
            continue
        parts = [p.strip() for p in stripped.split("|")]
        if len(parts) > 1:
            ids.append(parts[1])
    return ids


def test_requirement_ids_unique_and_complete() -> None:
    text = _matrix_text()
    reqs = _requirement_definition_ids(text)
    assert len(reqs) == 67, f"se esperaban 67 filas de requisito, hay {len(reqs)}"
    duplicates = sorted({r for r in reqs if reqs.count(r) > 1})
    assert not duplicates, "requirement IDs duplicados en las tablas: " + ", ".join(duplicates)
    assert (
        set(reqs) == _EXPECTED_REQ_IDS
    ), "el conjunto de requirement IDs no coincide con el esperado (67 IDs únicos)"


def test_no_requirement_row_without_acceptance_criteria() -> None:
    text = _matrix_text()
    empty: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("| REQ-"):
            continue
        parts = [p.strip() for p in stripped.split("|")]
        # parts = ['', REQ, Solicitud, Objetivo, AC, Impl, Prueba, Smoke, Evidencia, '']
        if len(parts) < 5 or not parts[4] or "AC-" not in parts[4]:
            empty.append(parts[1] if len(parts) > 1 else stripped)
    assert not empty, "filas de requisito sin AC: " + ", ".join(empty)


def test_requirement_rows_citing_a_test_point_to_existing_files() -> None:
    """Cada fila que exige prueba automatizada apunta a un archivo de test existente."""
    text = _matrix_text()
    text_by_line = text.splitlines()
    broken: list[str] = []
    for idx, line in enumerate(text_by_line):
        stripped = line.strip()
        if not stripped.startswith("| REQ-"):
            continue
        parts = [p.strip() for p in stripped.split("|")]
        if len(parts) < 7:
            continue
        req = parts[1]
        prueba_cell = parts[6]
        # Filas con verificación exclusivamente humana ("— (...)" sin path de test) son válidas.
        cited = _TEST_PATH_RE.findall(prueba_cell)
        for token in cited:
            path = token.split("::", 1)[0]
            if not (REPO_ROOT / path).exists():
                broken.append(f"{req} -> {path} (línea {idx + 1})")
    assert not broken, "filas de requisito que apuntan a archivo inexistente: " + "; ".join(broken)
