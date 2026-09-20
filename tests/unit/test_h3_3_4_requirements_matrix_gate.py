"""Gate programático de trazabilidad de la matriz H3.3.4 (endurecido, ronda 3).

Cierra F1/F9/F10 de ``evidence/H3.3.4/reviewer/review-03.json``.

La gramática canónica de referencias de prueba es estricta y auditable:

- Una referencia canónica es ``tests/unit/<archivo>.py`` o
  ``tests/integration/<archivo>.py`` y, cuando cita una función, la forma
  ``tests/<tipo>/<archivo>.py::test_nombre_exacto`` con el nombre exacto.
- El gate **inventaría todos los tokens con apariencia de referencia de prueba**
  dentro de la columna "Prueba automatizada" (§3/§4/§5) y "Prueba prevista" (§7),
  y rechaza cualquier token sospechoso que no coincida de extremo a extremo con la
  gramática canónica. Una celda con una referencia válida y otra inválida **falla**.
- Cada referencia canónica se valida contra el filesystem y contra el AST del
  archivo real: sólo se acepta una función ``def``/``async def`` de nivel módulo
  cuyo nombre exacto comienza con ``test_`` (pytest colectable). No se aceptan
  helpers, coincidencias parciales ni nombres presentes sólo en comentarios o
  strings. No se agrega gramática para métodos de clase ``Test*`` porque la matriz
  actual no los necesita.
- Las referencias deben ir dentro de code spans Markdown; una referencia con
  apariencia de test fuera de code span se rechaza explícitamente.
- El gate cruza el mapeo §6 (AC → REQ) con la columna AC de cada fila REQ **en
  ambos sentidos**: §6[AC] debe coincidir exactamente con el conjunto de filas que
  asignan ese AC, y el conjunto de REQ de §6 debe coincidir con las 67 filas.

No se usa ``tests/security/`` en la gramática de esta matriz porque las referencias
de esta tarea se normalizan a ``tests/unit/``/``tests/integration/``. Ese directorio
**sí existe** (p. ej. ``tests/security/test_eb_deployment_security.py``) y no se
incorpora sólo por restricción de gramática, no por inexistencia; ninguna cobertura
exigida se pierde por ello (REQ-S-07/AC-7 sigue siendo Human Gate).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX = REPO_ROOT / "docs" / "H3_3_4_REQUIREMENTS_MATRIX.md"

# --- Gramática canónica ------------------------------------------------------

# Referencia canónica completa (fullmatch): tests/(unit|integration)/test_<f>.py
# con función opcional `::test_<nombre>` exacta.
_CANONICAL_REF_RE = re.compile(
    r"tests/(?:unit|integration)/test_[A-Za-z0-9_]+\.py(?:::test_[A-Za-z0-9_]+)?"
)

# Token con apariencia de ruta de prueba (`...py[::nombre]`) o `::nombre` desnudo.
# Se usa para inventariar TODOS los fragmentos sospechosos de una celda; luego cada
# fragmento debe fullmatchear la gramática canónica o provocar un fallo explícito.
_PATH_TOKEN_RE = re.compile(r"[\w./\\-]+\.py(?:::\w+)*|(?<![\w.])::\w+")

# Pista de directorio de prueba: `tests/`, `./tests/`, `/tests/`, `unit/`,
# `integration/` (formas parciales que deben rechazarse).
_TEST_DIR_HINT_RE = re.compile(r"^(?:\.{0,2}/|/)?(?:tests|unit|integration)/")

_REQ_ID_RE = re.compile(r"\bREQ-[A-Z]+-\d{2}\b")
_AC_ID_RE = re.compile(r"\bAC-\d{1,2}\b")

_EXPECTED_REQ_IDS = {
    *(f"REQ-A-{i:02d}" for i in range(1, 25)),
    *(f"REQ-B-{i:02d}" for i in range(1, 31)),
    *(f"REQ-S-{i:02d}" for i in range(1, 14)),
}
_EXPECTED_TC_IDS = {f"TC-{i}" for i in range(1, 22)}

# AC con verificación exclusivamente humana (sin prueba automatizada obligatoria).
_HUMAN_ONLY_ACS = {"AC-5", "AC-6", "AC-7", "AC-9"}
_AUTOMATED_ACS = {f"AC-{i}" for i in range(1, 19)} - _HUMAN_ONLY_ACS

# Filas cuya verificación no es un pytest individual: smoke humano en AWS DEV (parte
# humana de un AC "both") o gate de CI/guard del Harness. Whitelist mínima y documentada.
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
    return MATRIX.read_text(encoding="utf-8-sig")


def _cells(line: str) -> list[str]:
    """Split a markdown table row into trimmed cells (dropping the outer pipes)."""
    return [c.strip() for c in line.split("|")[1:-1]]


def _column_indices(text: str) -> dict[str, int]:
    """Localiza la columna exacta "Prueba automatizada" y "Prueba prevista" por su
    cabecera, en lugar de asumir un índice fijo."""
    indices: dict[str, int] = {}
    for line in text.splitlines():
        s = line.strip()
        if not (s.startswith("|") and s.count("|") >= 2):
            continue
        for j, cell in enumerate(_cells(s)):
            name = cell.strip()
            if name in ("Prueba automatizada", "Prueba prevista") and name not in indices:
                indices[name] = j
    if "Prueba automatizada" not in indices or "Prueba prevista" not in indices:
        raise AssertionError("no se localizaron las columnas de prueba en la matriz")
    return indices


def _requirement_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("| REQ-"):
            continue
        cells = _cells(stripped)
        if cells and cells[0].startswith("REQ-"):
            rows.append(cells)
    return rows


def _tc_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("| TC-"):
            continue
        cells = _cells(stripped)
        if cells and cells[0].startswith("TC-"):
            rows.append(cells)
    return rows


def _section6_map(text: str) -> dict[str, set[str]]:
    """Mapeo §6 AC → conjunto de REQ (columna "Requirement IDs de origen")."""
    mapping: dict[str, set[str]] = {}
    in_section = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## 6."):
            in_section = True
            continue
        if s.startswith("## 7."):
            break
        if in_section and s.startswith("| AC-"):
            cells = _cells(s)
            if len(cells) >= 2:
                mapping[cells[0].strip()] = set(_REQ_ID_RE.findall(cells[1]))
    return mapping


def _expand_acs(cell: str) -> set[str]:
    """Expande la columna AC, incluyendo rangos como `AC-4..AC-10`."""
    acs: set[str] = set()
    for match in re.finditer(r"AC-(\d{1,2})\s*\.\.\s*AC-(\d{1,2})", cell):
        lo, hi = int(match.group(1)), int(match.group(2))
        acs.update(f"AC-{i}" for i in range(lo, hi + 1))
    without_ranges = re.sub(r"AC-\d{1,2}\s*\.\.\s*AC-\d{1,2}", " ", cell)
    for match in re.finditer(r"AC-(\d{1,2})", without_ranges):
        acs.add(match.group(0))
    return acs


def _path_tokens(text: str) -> list[str]:
    return _PATH_TOKEN_RE.findall(text)


def _is_test_like(token: str) -> bool:
    """True si el token tiene apariencia de referencia de prueba (vs. ruta de
    implementación/evidencia/benchmark como ``scripts/benchmark_executive_dashboard.py``)."""
    if token.startswith("::"):
        return True
    path = token.split("::", 1)[0].replace("\\", "/")
    if path.rsplit("/", 1)[-1].startswith("test_"):
        return True
    if _TEST_DIR_HINT_RE.match(path):
        return True
    return False


def _module_test_functions(path: Path) -> set[str]:
    """Devuelve los nombres de funciones `def`/`async def` de nivel módulo que
    comienzan con `test_`, parseando el archivo con `ast` (no con regex sobre el
    texto): los nombres presentes sólo en comentarios/strings no cuentan."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (SyntaxError, OSError):
        return set()
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def _validate_canonical_ref(req: str, token: str) -> str | None:
    """Valida una referencia canónica contra filesystem + AST. Devuelve el error o None."""
    if not _CANONICAL_REF_RE.fullmatch(token):
        return f"{req}: referencia de prueba no canónica: {token}"
    path_part, _, name = token.partition("::")
    path = REPO_ROOT / path_part
    if not path.exists():
        return f"{req}: ruta de prueba inexistente: {path_part}"
    if name:
        if name not in _module_test_functions(path):
            return f"{req}: función de prueba inexistente o no colectable: {path_part}::{name}"
    return None


def _validate_test_cell(req: str, cell: str) -> tuple[list[str], list[str]]:
    """Valida una celda "Prueba automatizada"/"Prueba prevista".

    Inventaría todos los tokens con apariencia de referencia de prueba y exige que
    cada uno coincida de extremo a extremo con la gramática canónica y resuelva.
    Devuelve ``(errors, refs)`` donde ``refs`` son las referencias canónicas válidas.
    """
    errors: list[str] = []
    refs: list[str] = []

    # 1. Referencias con apariencia de test fuera de code span → rechazo explícito.
    outside = re.sub(r"`[^`]*`", " ", cell)
    for token in _path_tokens(outside):
        if _is_test_like(token):
            errors.append(f"{req}: referencia de prueba fuera de code span: {token}")

    # 2. Cada code span sospechoso debe ser una referencia canónica que resuelva.
    for span in re.findall(r"`([^`]*)`", cell):
        for token in _path_tokens(span):
            if not _is_test_like(token):
                continue
            error = _validate_canonical_ref(req, token)
            if error is not None:
                errors.append(error)
            else:
                refs.append(token)

    return errors, refs


def _validate(text: str) -> list[str]:
    """Devuelve la lista completa de violaciones de trazabilidad (vacío == PASS)."""
    errors: list[str] = []

    # 1. Sin referencia a tareas posteriores.
    if "H3.3.5" in text:
        errors.append("la matriz referencia una tarea posterior H3.3.5")

    # 2. Localizar las columnas de prueba por cabecera.
    col = _column_indices(text)

    # 3. Filas de requisito: columna de prueba, AC y whitelist.
    req_rows = _requirement_rows(text)
    req_ids = [cells[0] for cells in req_rows]
    row_info: list[tuple[str, set[str], list[str]]] = []
    for cells in req_rows:
        req = cells[0]
        ac_cell = cells[3] if len(cells) > 3 else ""
        row_acs = _expand_acs(ac_cell)
        if not row_acs:
            errors.append(f"{req}: fila sin criterio de aceptación (AC)")
        prueba_cell = (
            cells[col["Prueba automatizada"]] if len(cells) > col["Prueba automatizada"] else ""
        )
        cell_errors, refs = _validate_test_cell(req, prueba_cell)
        errors.extend(cell_errors)
        row_info.append((req, row_acs, refs))

    for req, row_acs, refs in row_info:
        if row_acs.intersection(_AUTOMATED_ACS) and req not in _NON_PYTEST_VERIFIED_REQS:
            if not refs:
                errors.append(
                    f"{req}: fila con AC automatizado sin referencia de prueba verificable"
                )
        if not refs and req not in _NON_PYTEST_VERIFIED_REQS:
            if not (row_acs and row_acs <= _HUMAN_ONLY_ACS):
                errors.append(
                    f"{req}: fila sin prueba automatizada cuyos AC no son exclusivamente "
                    f"humanos ({sorted(row_acs)})"
                )

    # 4. Filas de casos de prueba (§7).
    tc_ids: list[str] = []
    for cells in _tc_rows(text):
        tc = cells[0]
        tc_ids.append(tc)
        prueba_cell = cells[col["Prueba prevista"]] if len(cells) > col["Prueba prevista"] else ""
        cell_errors, _ = _validate_test_cell(tc, prueba_cell)
        errors.extend(cell_errors)

    # 5. Conjunto exacto de requisitos (67 IDs únicos y completos).
    if len(req_ids) != 67:
        errors.append(f"se esperaban 67 filas de requisito, hay {len(req_ids)}")
    duplicates = sorted({r for r in req_ids if req_ids.count(r) > 1})
    if duplicates:
        errors.append("requirement IDs duplicados: " + ", ".join(duplicates))
    if set(req_ids) != _EXPECTED_REQ_IDS:
        errors.append("el conjunto de requirement IDs no coincide con los 67 IDs esperados")

    # 6. Conjunto exacto de casos de prueba (TC-1..TC-21).
    if set(tc_ids) != _EXPECTED_TC_IDS:
        errors.append("el conjunto de TC IDs no coincide con TC-1..TC-21")

    # 7. Consistencia bidireccional §6 ↔ columna AC de cada fila REQ.
    sec6 = _section6_map(text)
    rows_map: dict[str, set[str]] = {}
    for req, row_acs, _ in row_info:
        for ac in row_acs:
            rows_map.setdefault(ac, set()).add(req)

    for i in range(1, 19):
        ac = f"AC-{i}"
        s6 = sec6.get(ac, set())
        rv = rows_map.get(ac, set())
        if not rv:
            errors.append(f"{ac}: cobertura perdida (ninguna fila REQ lo asigna)")
        if s6 != rv:
            errors.append(
                f"{ac}: inconsistencia §6↔filas "
                f"(solo §6: {sorted(s6 - rv)}; solo filas: {sorted(rv - s6)})"
            )

    s6_reqs = set().union(*sec6.values()) if sec6 else set()
    if s6_reqs != set(req_ids):
        errors.append("los requirement IDs de §6 no coinciden con las filas de requisito")

    return errors


# --------------------------------------------------------------------------- #
# Gate positivo (ejecutado contra la matriz real)
# --------------------------------------------------------------------------- #


def test_requirements_matrix_passes_the_traceability_gate() -> None:
    errors = _validate(_matrix_text())
    assert not errors, "violaciones de trazabilidad:\n- " + "\n- ".join(errors)


def test_all_references_in_test_columns_are_canonical_and_resolvable() -> None:
    text = _matrix_text()
    col = _column_indices(text)
    collected: list[str] = []
    for cells in _requirement_rows(text):
        cell = cells[col["Prueba automatizada"]]
        for span in re.findall(r"`([^`]*)`", cell):
            for token in _path_tokens(span):
                if _is_test_like(token):
                    collected.append(token)
    for cells in _tc_rows(text):
        cell = cells[col["Prueba prevista"]]
        for span in re.findall(r"`([^`]*)`", cell):
            for token in _path_tokens(span):
                if _is_test_like(token):
                    collected.append(token)
    assert collected, "no se encontraron referencias de prueba en las columnas de prueba"
    for token in collected:
        assert _CANONICAL_REF_RE.fullmatch(token), f"referencia no canónica: {token}"
        path_part, _, name = token.partition("::")
        assert (REPO_ROOT / path_part).exists(), f"ruta inexistente: {path_part}"
        if name:
            assert name in _module_test_functions(
                REPO_ROOT / path_part
            ), f"función inexistente o no colectable: {token}"


def test_no_reference_to_follow_up_task_h3_3_5() -> None:
    assert "H3.3.5" not in _matrix_text()


def test_acceptance_criteria_1_to_18_present() -> None:
    errors = _validate(_matrix_text())
    coverage = [e for e in errors if "cobertura perdida" in e]
    assert not coverage, "AC sin cobertura: " + ", ".join(coverage)


def test_requirement_ids_unique_and_complete() -> None:
    req_ids = [cells[0] for cells in _requirement_rows(_matrix_text())]
    assert len(req_ids) == 67, f"se esperaban 67 filas de requisito, hay {len(req_ids)}"
    assert set(req_ids) == _EXPECTED_REQ_IDS
    duplicates = sorted({r for r in req_ids if req_ids.count(r) > 1})
    assert not duplicates, "requirement IDs duplicados: " + ", ".join(duplicates)


def test_test_case_ids_unique_and_complete() -> None:
    tc_ids = [cells[0] for cells in _tc_rows(_matrix_text())]
    assert set(tc_ids) == _EXPECTED_TC_IDS, f"TC IDs inesperados: {sorted(set(tc_ids))}"


def test_no_requirement_row_without_acceptance_criteria() -> None:
    for cells in _requirement_rows(_matrix_text()):
        assert "AC-" in cells[3], f"{cells[0]}: fila sin AC"


def test_automated_rows_cite_a_verifiable_test_in_the_test_column() -> None:
    text = _matrix_text()
    col = _column_indices(text)
    for cells in _requirement_rows(text):
        req = cells[0]
        row_acs = _expand_acs(cells[3])
        if row_acs.intersection(_AUTOMATED_ACS) and req not in _NON_PYTEST_VERIFIED_REQS:
            _, refs = _validate_test_cell(req, cells[col["Prueba automatizada"]])
            assert refs, f"{req}: fila automatizada sin referencia de prueba verificable"


def test_human_only_rows_map_to_human_acceptance_criteria() -> None:
    text = _matrix_text()
    col = _column_indices(text)
    for cells in _requirement_rows(text):
        req = cells[0]
        _, refs = _validate_test_cell(req, cells[col["Prueba automatizada"]])
        if not refs and req not in _NON_PYTEST_VERIFIED_REQS:
            row_acs = _expand_acs(cells[3])
            assert row_acs and row_acs <= _HUMAN_ONLY_ACS, (
                f"{req}: fila sin prueba automatizada cuyos AC no son exclusivamente "
                f"humanos ({sorted(row_acs)})"
            )


def test_section6_mapping_matches_row_acceptance_criteria_bidirectionally() -> None:
    errors = _validate(_matrix_text())
    inconsistencies = [e for e in errors if "inconsistencia §6↔filas" in e]
    assert not inconsistencies, "inconsistencias §6↔filas:\n- " + "\n- ".join(inconsistencies)


# --------------------------------------------------------------------------- #
# Gate negativo: el MISMO validador sobre copias mutadas de la matriz
# --------------------------------------------------------------------------- #

_MATRIX_ORIGINAL = _matrix_text()


def _assert_gate_fails(mutated: str, fragment: str) -> list[str]:
    """Ejecuta el validador real sobre una matriz mutada y verifica que falle por la
    razón esperada (mensaje/categoría relevante), no sólo que falle."""
    errors = _validate(mutated)
    assert errors, "el gate debería fallar ante la mutación, pero pasó"
    assert any(
        fragment in e for e in errors
    ), f"el gate falló, pero no por la razón esperada ({fragment!r}): {errors}"
    return errors


def _set_row_cell(text: str, row_prefix: str, col_index: int, new_cell: str) -> str:
    """Reemplaza una columna de una fila concreta (por prefijo de la primera celda)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith(row_prefix):
            cells = _cells(line.strip())
            cells[col_index] = new_cell
            lines[i] = "| " + " | ".join(cells) + " |"
            return "\n".join(lines)
    raise AssertionError(f"fila no encontrada: {row_prefix}")


def _remove_req_from_section6(text: str, ac_id: str, req_id: str) -> str:
    """Quita un REQ de la columna de orígenes de una fila AC en §6."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith(f"| {ac_id} |"):
            cells = _cells(line.strip())
            reqs = [r.strip() for r in cells[1].split(",") if r.strip()]
            reqs = [r for r in reqs if r != req_id]
            cells[1] = ", ".join(reqs)
            lines[i] = "| " + " | ".join(cells) + " |"
            return "\n".join(lines)
    raise AssertionError(f"{ac_id} no encontrado en §6")


# Anclas únicas (referencias que aparecen una sola vez en la matriz real).
_ANCHOR_SINGLE_LEAD = (
    "`tests/integration/test_executive_dashboard_repository.py::test_single_lead_metrics`"
)
_ANCHOR_TIEMPO = (
    "`tests/integration/test_executive_dashboard_repository.py::test_tiempo_asignacion_media`"
)
_ANCHOR_FANOUT = "tests/integration/test_executive_dashboard_per_advisor.py::test_cartera_por_asesor_fanout_safe_and_dimensional_filter"


def test_gate_rejects_partial_path_integration_alongside_valid_reference() -> None:
    """1. `integration/...::test_inexistente` junto a una referencia válida."""
    mutated = _MATRIX_ORIGINAL.replace(
        _ANCHOR_SINGLE_LEAD,
        _ANCHOR_SINGLE_LEAD
        + ", `integration/test_executive_dashboard_per_advisor.py::test_ghost_never_written`",
    )
    _assert_gate_fails(mutated, "referencia de prueba no canónica")


def test_gate_rejects_partial_path_unit_alongside_valid_reference() -> None:
    """2. `unit/...::test_inexistente` junto a una válida."""
    mutated = _MATRIX_ORIGINAL.replace(
        _ANCHOR_SINGLE_LEAD,
        _ANCHOR_SINGLE_LEAD
        + ", `unit/test_executive_dashboard_access.py::test_ghost_never_written`",
    )
    _assert_gate_fails(mutated, "referencia de prueba no canónica")


def test_gate_rejects_dot_slash_tests_path_alongside_valid_reference() -> None:
    """3. `./tests/integration/...::test_inexistente` junto a una válida."""
    mutated = _MATRIX_ORIGINAL.replace(
        _ANCHOR_SINGLE_LEAD,
        _ANCHOR_SINGLE_LEAD
        + ", `./tests/integration/test_executive_dashboard_repository.py::test_ghost_never_written`",
    )
    _assert_gate_fails(mutated, "referencia de prueba no canónica")


def test_gate_rejects_leading_slash_tests_path() -> None:
    """4. `/tests/unit/...::test_inexistente`."""
    mutated = _MATRIX_ORIGINAL.replace(
        _ANCHOR_SINGLE_LEAD,
        _ANCHOR_SINGLE_LEAD
        + ", `/tests/unit/test_executive_dashboard_access.py::test_ghost_never_written`",
    )
    _assert_gate_fails(mutated, "referencia de prueba no canónica")


def test_gate_rejects_security_dir_reference() -> None:
    """5. `tests/security/...::test_inexistente` (directorio real pero fuera de gramática)."""
    mutated = _MATRIX_ORIGINAL.replace(
        _ANCHOR_SINGLE_LEAD,
        _ANCHOR_SINGLE_LEAD
        + ", `tests/security/test_eb_deployment_security.py::test_ghost_never_written`",
    )
    _assert_gate_fails(mutated, "referencia de prueba no canónica")


def test_gate_rejects_unknown_test_dir_reference() -> None:
    """6. `tests/otro/...::test_inexistente`."""
    mutated = _MATRIX_ORIGINAL.replace(
        _ANCHOR_SINGLE_LEAD,
        _ANCHOR_SINGLE_LEAD + ", `tests/otro/test_ghost.py::test_ghost`",
    )
    _assert_gate_fails(mutated, "referencia de prueba no canónica")


def test_gate_rejects_bare_test_file_reference() -> None:
    """7. `test_archivo.py::test_inexistente` (sin prefijo `tests/`)."""
    mutated = _MATRIX_ORIGINAL.replace(
        _ANCHOR_SINGLE_LEAD,
        _ANCHOR_SINGLE_LEAD + ", `test_ghost.py::test_ghost`",
    )
    _assert_gate_fails(mutated, "referencia de prueba no canónica")


def test_gate_rejects_bare_function_reference() -> None:
    """8. `::test_does_not_exist_anywhere` (función desnuda sin ruta)."""
    mutated = _MATRIX_ORIGINAL.replace(
        _ANCHOR_SINGLE_LEAD,
        _ANCHOR_SINGLE_LEAD + ", `::test_does_not_exist_anywhere`",
    )
    _assert_gate_fails(mutated, "referencia de prueba no canónica")


def test_gate_rejects_existing_path_with_nonexistent_function() -> None:
    """9. Ruta real + función inexistente."""
    mutated = _MATRIX_ORIGINAL.replace(
        _ANCHOR_SINGLE_LEAD,
        "`tests/integration/test_executive_dashboard_repository.py::test_does_not_exist_here`",
    )
    _assert_gate_fails(mutated, "función de prueba inexistente o no colectable")


def test_gate_rejects_helper_function_reference() -> None:
    """10. Ruta real + helper `::_make_lead` (no test)."""
    mutated = _MATRIX_ORIGINAL.replace(
        _ANCHOR_SINGLE_LEAD,
        "`tests/integration/test_executive_dashboard_repository.py::_make_lead`",
    )
    _assert_gate_fails(mutated, "referencia de prueba no canónica")


def test_gate_rejects_partial_function_name() -> None:
    """11. Ruta real + nombre parcial de una prueba existente."""
    mutated = _MATRIX_ORIGINAL.replace(
        _ANCHOR_SINGLE_LEAD,
        "`tests/integration/test_executive_dashboard_repository.py::test_single_lead`",
    )
    _assert_gate_fails(mutated, "función de prueba inexistente o no colectable")


def test_gate_rejects_reference_outside_code_span() -> None:
    """12. Referencia inválida fuera de code span."""
    mutated = _MATRIX_ORIGINAL.replace(
        _ANCHOR_SINGLE_LEAD,
        _ANCHOR_SINGLE_LEAD
        + ", integration/test_executive_dashboard_per_advisor.py::test_ghost_never_written",
    )
    _assert_gate_fails(mutated, "referencia de prueba fuera de code span")


def test_gate_rejects_invalid_reference_alongside_two_valid_references() -> None:
    """13. Referencia inválida junto a dos referencias válidas (no queda oculta)."""
    mutated = _MATRIX_ORIGINAL.replace(
        _ANCHOR_SINGLE_LEAD,
        _ANCHOR_SINGLE_LEAD + ", `tests/otro/test_ghost.py::test_ghost`",
    )
    _assert_gate_fails(mutated, "referencia de prueba no canónica")


def test_gate_rejects_removing_an_ac_from_a_req_row_but_keeping_it_in_section6() -> None:
    """14. Quitar AC-12 sólo de una fila REQ, manteniéndolo en §6."""
    mutated = _set_row_cell(_MATRIX_ORIGINAL, "| REQ-B-13 |", 3, "")
    _assert_gate_fails(mutated, "inconsistencia §6↔filas")


def test_gate_rejects_adding_an_ac_to_a_req_row_not_in_section6() -> None:
    """15. Agregar un AC sólo a una fila (no en §6)."""
    mutated = _set_row_cell(_MATRIX_ORIGINAL, "| REQ-B-05 |", 3, "AC-11, AC-12")
    _assert_gate_fails(mutated, "inconsistencia §6↔filas")


def test_gate_rejects_removing_a_req_row_but_keeping_it_in_section6() -> None:
    """16. Eliminar REQ de la tabla pero conservarlo en §6."""
    line = next(ln for ln in _MATRIX_ORIGINAL.splitlines() if ln.strip().startswith("| REQ-B-05 |"))
    mutated = _MATRIX_ORIGINAL.replace(line + "\n", "")
    _assert_gate_fails(mutated, "inconsistencia §6↔filas")


def test_gate_rejects_removing_a_req_from_section6_but_keeping_it_in_the_table() -> None:
    """17. Eliminar REQ de §6 pero conservarlo en la tabla."""
    mutated = _remove_req_from_section6(_MATRIX_ORIGINAL, "AC-11", "REQ-B-05")
    _assert_gate_fails(mutated, "inconsistencia §6↔filas")


def test_gate_rejects_replacing_an_expected_req_id_keeping_67_rows() -> None:
    """18. Sustituir un ID esperado por otro nuevo manteniendo el total 67."""
    mutated = _set_row_cell(_MATRIX_ORIGINAL, "| REQ-B-05 |", 0, "REQ-B-99")
    _assert_gate_fails(mutated, "el conjunto de requirement IDs no coincide")


def test_gate_rejects_duplicating_a_requirement_row() -> None:
    """19. Duplicar un REQ."""
    line = next(ln for ln in _MATRIX_ORIGINAL.splitlines() if ln.strip().startswith("| REQ-B-05 |"))
    mutated = _MATRIX_ORIGINAL.replace(line, line + "\n" + line)
    _assert_gate_fails(mutated, "requirement IDs duplicados")


def test_gate_rejects_removing_all_coverage_of_an_ac() -> None:
    """20. Eliminar toda cobertura de un AC (AC-16)."""
    mutated = _MATRIX_ORIGINAL.replace("AC-16", "")
    _assert_gate_fails(mutated, "cobertura perdida")


def test_gate_rejects_function_that_only_exists_in_comment_or_string() -> None:
    """21. Función mencionada únicamente en comentario/string, no definida."""
    probe = REPO_ROOT / "tests" / "unit" / "test_gate_probe_comment_only.py"
    probe.write_text(
        "# def test_only_in_comment(): pass\n"
        '"""def test_only_in_docstring(): pass"""\n'
        'x = "def test_only_in_string(): pass"\n',
        encoding="utf-8",
    )
    try:
        mutated = _MATRIX_ORIGINAL.replace(
            _ANCHOR_SINGLE_LEAD,
            "`tests/unit/test_gate_probe_comment_only.py::test_only_in_comment`",
        )
        _assert_gate_fails(mutated, "función de prueba inexistente o no colectable")
    finally:
        probe.unlink(missing_ok=True)


def test_gate_rejects_the_exact_bypass_from_review_round_3() -> None:
    """22. Patrón exacto que pasó en la ronda 3: `integration/...` (quitar `tests/`)."""
    mutated = _MATRIX_ORIGINAL.replace(
        _ANCHOR_FANOUT,
        "integration/test_executive_dashboard_per_advisor.py::test_cartera_por_asesor_fanout_safe_and_dimensional_filter",
    )
    _assert_gate_fails(mutated, "referencia de prueba no canónica")
