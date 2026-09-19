"""Gate programático de trazabilidad de la matriz H3.3.4 (endurecido, ronda 2).

Cierra F1 de ``evidence/H3.3.4/reviewer/review-02.json``. La gramática canónica de
referencias de prueba es estricta y auditable:

- Toda referencia a un archivo de prueba usa la ruta completa desde la raíz:
  ``tests/unit/<archivo>.py`` o ``tests/integration/<archivo>.py``.
- Toda referencia a una función concreta usa ``tests/<tipo>/<archivo>.py::test_nombre_exacto``.
- Quedan prohibidos: ``test_archivo.py`` sin prefijo ``tests/...``, ``::test_nombre``
  sin archivo, nombres parciales, referencias a archivos planificados y rutas de
  directorios no canónicos (``tests/security``/``tests/e2e``).

El gate inspecciona explícitamente la columna "Prueba automatizada" de las tablas
§3/§4/§5 y la columna "Prueba prevista" de la tabla §7, y además barre el documento
completo para detectar referencias abreviadas escondidas fuera de esas columnas.

Filas sin prueba automatizada (verificación exclusivamente humana) se identifican con
una regla explícita: su columna AC sólo contiene AC humanos (AC-5/AC-6/AC-7/AC-9).
Las filas con AC automatizados verificadas por CI/guard (no por un pytest) se listan
en una whitelist mínima documentada.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX = REPO_ROOT / "docs" / "H3_3_4_REQUIREMENTS_MATRIX.md"

# --- Gramática canónica ------------------------------------------------------

# Referencia canónica: tests/<unit|integration>/<archivo>.py[::test_nombre]
_FULL_REF_RE = re.compile(r"tests/(?:unit|integration)/[\w-]+\.py(?:::[A-Za-z_]\w*)?")

# `test_archivo.py` sin prefijo `tests/...` (el defecto exacto de 5ffb2a2).
_BARE_FILE_RE = re.compile(r"(?<![\w./-])test_[A-Za-z0-9_]+\.py")

# `::test_nombre` sin ruta completa asociada (no precedido por `.py`).
_ABBREV_FN_RE = re.compile(r"(?<!\.py)::[A-Za-z_]\w*")

# Directorios de prueba no canónicos para esta matriz.
_NON_CANONICAL_DIR_RE = re.compile(r"tests/(?:security|e2e)/[\w.-]*")

_REQ_ID_RE = re.compile(r"\bREQ-[A-Z]+-\d{2}\b")
_AC_ID_RE = re.compile(r"\bAC-\d{1,2}\b")
_FN_DEF_RE = re.compile(r"^\s*def\s+([A-Za-z_]\w*)\s*\(", re.MULTILINE)

_EXPECTED_REQ_IDS = {
    *(f"REQ-A-{i:02d}" for i in range(1, 25)),
    *(f"REQ-B-{i:02d}" for i in range(1, 31)),
    *(f"REQ-S-{i:02d}" for i in range(1, 14)),
}

# AC con verificación exclusivamente humana (sin prueba automatizada obligatoria).
_HUMAN_ONLY_ACS = {"AC-5", "AC-6", "AC-7", "AC-9"}
_AUTOMATED_ACS = {f"AC-{i}" for i in range(1, 19)} - _HUMAN_ONLY_ACS

# Filas cuya verificación no es un pytest individual: smoke humano en AWS DEV (parte
# humana de un AC "both") o gate de CI/guard del Harness. Whitelist mínima y documentada
# (nunca una excepción genérica).
_NON_PYTEST_VERIFIED_REQS: dict[str, str] = {
    "REQ-B-30": (
        "smoke humano completo en AWS DEV (parte humana de AC-18); sin prueba automatizada "
        "aplicable, verificado en la etapa Deployer/Verifying"
    ),
    "REQ-S-13": (
        "cobertura >=85% verificada por el job de CI (pytest --cov=app --cov-fail-under=85); "
        "no existe un pytest individual que mida la cobertura global"
    ),
}


def _matrix_text() -> str:
    assert MATRIX.exists(), f"no existe la matriz de trazabilidad: {MATRIX}"
    return MATRIX.read_text(encoding="utf-8")


def _cells(line: str) -> list[str]:
    """Split a markdown table row into trimmed cells (dropping the outer pipes)."""
    return [c.strip() for c in line.split("|")[1:-1]]


def _requirement_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("| REQ-"):
            continue
        cells = _cells(stripped)
        if len(cells) >= 6 and cells[0].startswith("REQ-"):
            rows.append(cells)
    return rows


def _tc_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("| TC-"):
            continue
        cells = _cells(stripped)
        if len(cells) >= 5 and cells[0].startswith("TC-"):
            rows.append(cells)
    return rows


def _file_functions(path: Path) -> set[str]:
    source = path.read_text(encoding="utf-8")
    return set(_FN_DEF_RE.findall(source))


def _validate_test_cell(req: str, cell: str) -> tuple[list[str], list[str]]:
    """Validate a "Prueba automatizada"/"Prueba prevista" cell.

    Returns ``(errors, full_refs)`` where ``full_refs`` are the canonical references
    (``tests/unit/...`` or ``tests/integration/...``) found in the cell.
    """
    errors: list[str] = []

    for token in _BARE_FILE_RE.findall(cell):
        errors.append(f"{req}: referencia sin prefijo tests/: {token}")
    for token in _ABBREV_FN_RE.findall(cell):
        errors.append(f"{req}: referencia ::test_* sin ruta completa: {token}")
    for token in _NON_CANONICAL_DIR_RE.findall(cell):
        errors.append(f"{req}: directorio de prueba no canónico: {token}")

    refs = _FULL_REF_RE.findall(cell)
    for ref in refs:
        if "::" in ref:
            path_part, name = ref.split("::", 1)
        else:
            path_part, name = ref, None
        path = REPO_ROOT / path_part
        if not path.exists():
            errors.append(f"{req}: ruta de prueba inexistente: {path_part}")
            continue
        if name is not None:
            if name not in _file_functions(path):
                errors.append(f"{req}: función de prueba inexistente: {path_part}::{name}")
    return errors, refs


def _validate(text: str) -> list[str]:
    """Return the full list of traceability violations (empty == PASS)."""
    errors: list[str] = []

    # 1. Gramática canónica en todo el documento (atrapa referencias fuera de las
    #    columnas inspeccionadas; el parser no ignora rutas narrativas abreviadas).
    for token in _BARE_FILE_RE.findall(text):
        errors.append(f"referencia abreviada sin prefijo tests/: {token}")
    for token in _ABBREV_FN_RE.findall(text):
        errors.append(f"referencia ::test_* sin ruta completa: {token}")
    for token in _NON_CANONICAL_DIR_RE.findall(text):
        errors.append(f"directorio de prueba no canónico: {token}")

    # 2. Sin referencia a tareas posteriores.
    if "H3.3.5" in text:
        errors.append("la matriz referencia una tarea posterior H3.3.5")

    # 3. AC-1..AC-18 presentes.
    acs = set(_AC_ID_RE.findall(text))
    for i in range(1, 19):
        if f"AC-{i}" not in acs:
            errors.append(f"AC-{i} ausente de la matriz")

    # 4. Filas de requisito: columna de prueba, AC y whitelist.
    req_rows = _requirement_rows(text)
    req_ids = [cells[0] for cells in req_rows]
    for cells in req_rows:
        req = cells[0]
        ac_cell = cells[3] if len(cells) > 3 else ""
        prueba_cell = cells[5] if len(cells) > 5 else ""

        row_acs = set(_AC_ID_RE.findall(ac_cell))
        if not row_acs:
            errors.append(f"{req}: fila sin criterio de aceptación (AC)")

        cell_errors, refs = _validate_test_cell(req, prueba_cell)
        errors.extend(cell_errors)

        if row_acs.intersection(_AUTOMATED_ACS) and req not in _NON_PYTEST_VERIFIED_REQS:
            if not refs:
                errors.append(
                    f"{req}: fila con AC automatizado sin referencia de prueba verificable"
                )

    # 5. Filas de casos de prueba (§7).
    for cells in _tc_rows(text):
        req = cells[0]
        prueba_cell = cells[4] if len(cells) > 4 else ""
        cell_errors, _ = _validate_test_cell(req, prueba_cell)
        errors.extend(cell_errors)

    # 6. Conjunto de requisitos: 67 IDs únicos y completos (nadie borra una fila
    #    para evitar validarla, ni duplica un ID).
    if len(req_ids) != 67:
        errors.append(f"se esperaban 67 filas de requisito, hay {len(req_ids)}")
    duplicates = sorted({r for r in req_ids if req_ids.count(r) > 1})
    if duplicates:
        errors.append("requirement IDs duplicados: " + ", ".join(duplicates))
    if set(req_ids) != _EXPECTED_REQ_IDS:
        errors.append("el conjunto de requirement IDs no coincide con los 67 IDs esperados")

    return errors


# --------------------------------------------------------------------------- #
# Gate positivo (ejecutado contra la matriz real)
# --------------------------------------------------------------------------- #


def test_requirements_matrix_passes_the_traceability_gate() -> None:
    errors = _validate(_matrix_text())
    assert not errors, "violaciones de trazabilidad:\n- " + "\n- ".join(errors)


def test_requirements_matrix_has_no_abbreviated_or_unprefixed_references() -> None:
    text = _matrix_text()
    assert not _BARE_FILE_RE.findall(text)
    assert not _ABBREV_FN_RE.findall(text)
    assert not _NON_CANONICAL_DIR_RE.findall(text)


def test_no_reference_to_follow_up_task_h3_3_5() -> None:
    assert "H3.3.5" not in _matrix_text()


def test_acceptance_criteria_1_to_18_present() -> None:
    text = _matrix_text()
    acs = set(_AC_ID_RE.findall(text))
    missing = [f"AC-{i}" for i in range(1, 19) if f"AC-{i}" not in acs]
    assert not missing, "AC faltantes en la matriz: " + ", ".join(missing)


def test_requirement_ids_unique_and_complete() -> None:
    req_ids = [cells[0] for cells in _requirement_rows(_matrix_text())]
    assert len(req_ids) == 67, f"se esperaban 67 filas de requisito, hay {len(req_ids)}"
    assert set(req_ids) == _EXPECTED_REQ_IDS
    duplicates = sorted({r for r in req_ids if req_ids.count(r) > 1})
    assert not duplicates, "requirement IDs duplicados: " + ", ".join(duplicates)


def test_no_requirement_row_without_acceptance_criteria() -> None:
    for cells in _requirement_rows(_matrix_text()):
        assert "AC-" in cells[3], f"{cells[0]}: fila sin AC"


def test_automated_rows_cite_a_verifiable_test_in_the_test_column() -> None:
    for cells in _requirement_rows(_matrix_text()):
        req = cells[0]
        row_acs = set(_AC_ID_RE.findall(cells[3]))
        if row_acs.intersection(_AUTOMATED_ACS) and req not in _NON_PYTEST_VERIFIED_REQS:
            prueba_cell = cells[5]
            assert _FULL_REF_RE.findall(
                prueba_cell
            ), f"{req}: fila automatizada sin referencia de prueba en la columna Prueba"


def test_human_only_rows_map_to_human_acceptance_criteria() -> None:
    for cells in _requirement_rows(_matrix_text()):
        req = cells[0]
        prueba_cell = cells[5]
        if not _FULL_REF_RE.findall(prueba_cell) and req not in _NON_PYTEST_VERIFIED_REQS:
            row_acs = set(_AC_ID_RE.findall(cells[3]))
            assert row_acs and row_acs <= _HUMAN_ONLY_ACS, (
                f"{req}: fila sin prueba automatizada cuyos AC no son exclusivamente "
                f"humanos ({sorted(row_acs)})"
            )


# --------------------------------------------------------------------------- #
# Gate negativo: el MISMO validador sobre copias mutadas de la matriz
# --------------------------------------------------------------------------- #

_MATRIX_ORIGINAL = _matrix_text()


def _assert_gate_fails(mutated: str) -> list[str]:
    """Run the real validator on a mutated matrix and assert it fails."""
    errors = _validate(mutated)
    assert errors, "el gate debería fallar ante la mutación, pero pasó"
    return errors


def test_gate_rejects_5ffb2a2_pattern_bare_nonexistent_test_file() -> None:
    """1. El patrón exacto que permitió F1 en 5ffb2a2: `test_*.py` sin prefijo."""
    mutated = _MATRIX_ORIGINAL.replace(
        "`tests/integration/test_executive_dashboard_repository.py::test_single_lead_metrics`",
        "`test_executive_dashboard_kpis.py::test_single_lead_metrics`",
    )
    _assert_gate_fails(mutated)


def test_gate_rejects_unprefixed_nonexistent_path() -> None:
    """2. Ruta inexistente escrita sin prefijo `tests/`."""
    mutated = _MATRIX_ORIGINAL.replace(
        "`tests/integration/test_executive_dashboard_repository.py::test_single_lead_metrics`",
        "`test_does_not_exist.py::test_single_lead_metrics`",
    )
    _assert_gate_fails(mutated)


def test_gate_rejects_abbreviated_nonexistent_function() -> None:
    """3. `::test_does_not_exist_anywhere` abreviado (sin ruta completa)."""
    mutated = _MATRIX_ORIGINAL.replace(
        "`tests/integration/test_executive_dashboard_repository.py::test_single_lead_metrics`",
        "`tests/integration/test_executive_dashboard_repository.py::test_single_lead_metrics`, "
        "`::test_does_not_exist_anywhere`",
    )
    _assert_gate_fails(mutated)


def test_gate_rejects_existing_path_with_nonexistent_function() -> None:
    """4. Ruta existente con función inexistente."""
    mutated = _MATRIX_ORIGINAL.replace(
        "`tests/integration/test_executive_dashboard_repository.py::test_single_lead_metrics`",
        "`tests/integration/test_executive_dashboard_repository.py::test_does_not_exist_here`",
    )
    _assert_gate_fails(mutated)


def test_gate_rejects_abbreviated_file_test_executive_dashboard() -> None:
    """5. Archivo abreviado `test_executive_dashboard.py`."""
    mutated = _MATRIX_ORIGINAL.replace(
        "`tests/integration/test_executive_dashboard_repository.py::test_single_lead_metrics`",
        "`test_executive_dashboard.py::test_single_lead_metrics`",
    )
    _assert_gate_fails(mutated)


def test_gate_rejects_removing_the_test_of_an_automated_row() -> None:
    """6. Eliminación de la prueba de una fila automatizada."""
    mutated = _MATRIX_ORIGINAL.replace(
        "`tests/integration/test_executive_dashboard_repository.py::test_tiempo_asignacion_media`",
        "— (cubierto por test)",
    )
    _assert_gate_fails(mutated)


def test_gate_rejects_removing_a_requirement_row() -> None:
    """7. Eliminación completa de una fila REQ."""
    line = next(ln for ln in _MATRIX_ORIGINAL.splitlines() if ln.strip().startswith("| REQ-B-05 |"))
    mutated = _MATRIX_ORIGINAL.replace(line + "\n", "")
    _assert_gate_fails(mutated)


def test_gate_rejects_duplicating_a_requirement_row() -> None:
    """8. Duplicación de un REQ."""
    line = next(ln for ln in _MATRIX_ORIGINAL.splitlines() if ln.strip().startswith("| REQ-B-05 |"))
    mutated = _MATRIX_ORIGINAL.replace(line, line + "\n" + line)
    _assert_gate_fails(mutated)


def test_gate_rejects_removing_an_acceptance_criterion() -> None:
    """9. Eliminación de la cobertura de un AC (AC-12 desaparece del documento)."""
    mutated = _MATRIX_ORIGINAL.replace("AC-12", "")
    _assert_gate_fails(mutated)


def test_gate_rejects_reference_placed_in_narrative_but_absent_from_test_column() -> None:
    """10. Referencia en texto narrativo pero ausente de la columna de prueba."""
    line = next(ln for ln in _MATRIX_ORIGINAL.splitlines() if ln.strip().startswith("| REQ-B-05 |"))
    cells = _cells(line.strip())
    # Move the test reference out of the "Prueba automatizada" column (index 5)
    # into the "Implementación prevista" column (index 4).
    mutated_cells = list(cells)
    mutated_cells[4] = mutated_cells[4] + " " + mutated_cells[5]
    mutated_cells[5] = "— (cubierto por test)"
    mutated_line = "| " + " | ".join(mutated_cells) + " |"
    mutated = _MATRIX_ORIGINAL.replace(line, mutated_line)
    _assert_gate_fails(mutated)
