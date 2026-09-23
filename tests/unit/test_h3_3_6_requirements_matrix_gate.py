"""Gate programático de trazabilidad de la matriz y la allowlist H3.3.6.

Verifica dos documentos canónicos creados por el Developer antes de tocar código
funcional:

- ``docs/H3_3_6_REQUIREMENTS_MATRIX.md``: todo AC (AC-1..AC-18) con cobertura, cada
  referencia de prueba canónica y resoluble contra filesystem + AST, y sin
  referencia a tareas posteriores (H3.3.7 / H3.3.8 / H3.2).
- ``docs/H3_3_6_EXPORT_COLUMNS.md``: allowlist exacta de 14 columnas (conjunto y
  orden) y exclusión explícita de ``raw_payload`` y campos de secretos.

Gramática canónica de referencia: ``tests/(unit|integration)/test_<f>.py`` con
función opcional ``::test_<nombre>``. Cada referencia debe ir en un code span
Markdown y resolverse al archivo real y a una función ``def``/``async def`` de
nivel módulo cuyo nombre exacto comienza con ``test_``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX = REPO_ROOT / "docs" / "H3_3_6_REQUIREMENTS_MATRIX.md"
COLUMNS = REPO_ROOT / "docs" / "H3_3_6_EXPORT_COLUMNS.md"

_CANONICAL_REF_RE = re.compile(
    r"tests/(?:unit|integration)/test_[A-Za-z0-9_]+\.py(?:::test_[A-Za-z0-9_]+)?"
)
_PATH_TOKEN_RE = re.compile(r"[\w./\\-]+\.py(?:::\w+)*|(?<![\w.])::\w+")

# Allowlist esperada (campo origen, en orden) — debe coincidir exactamente con la
# implementación ``app/services/xlsx_export.py::EXPORT_COLUMNS``.
_EXPECTED_FIELDS = [
    "id_lead",
    "rut",
    "nombre_completo",
    "email",
    "telefono",
    "genero",
    "estado_civil",
    "afp",
    "saldo_afp",
    "comentarios",
    "estado_lead",
    "created_at",
    "id_asesor",
    "asesor_nombre",
]

_FORBIDDEN_IN_MATRIX = ["H3.3.7", "H3.3.8", "H3.2"]


def _matrix_text() -> str:
    assert MATRIX.exists(), f"no existe la matriz: {MATRIX}"
    return MATRIX.read_text(encoding="utf-8-sig")


def _columns_text() -> str:
    assert COLUMNS.exists(), f"no existe la matriz de columnas: {COLUMNS}"
    return COLUMNS.read_text(encoding="utf-8-sig")


def _module_test_functions(path: Path) -> set[str]:
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


def _collect_references(text: str) -> list[str]:
    """Inventaría toda referencia con apariencia de prueba dentro de code spans."""
    refs: list[str] = []
    for span in re.findall(r"`([^`]*)`", text):
        for token in _PATH_TOKEN_RE.findall(span):
            if token.startswith("::") or "test_" in token or "/tests/" in token:
                refs.append(token)
    return refs


def _canonical_ref_errors(text: str) -> list[str]:
    errors: list[str] = []
    for span in re.findall(r"`([^`]*)`", text):
        for token in _PATH_TOKEN_RE.findall(span):
            if not (token.startswith("::") or "test_" in token or "/tests/" in token):
                continue
            if not _CANONICAL_REF_RE.fullmatch(token):
                errors.append(f"referencia de prueba no canónica: {token}")
                continue
            path_part, _, name = token.partition("::")
            path = REPO_ROOT / path_part
            if not path.exists():
                errors.append(f"ruta de prueba inexistente: {path_part}")
                continue
            if name and name not in _module_test_functions(path):
                errors.append(f"función de prueba inexistente o no colectable: {path_part}::{name}")
    return errors


def _ac_coverage_errors(text: str) -> list[str]:
    errors: list[str] = []
    for i in range(1, 19):
        ac = f"AC-{i}"
        if ac not in text:
            errors.append(f"{ac}: cobertura perdida (no aparece en la matriz)")
    return errors


def _allowlist_fields(text: str) -> list[str]:
    """Extrae los campos ``Campo origen`` de las filas numeradas de la allowlist."""
    fields: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and re.match(r"^\|\s*\d+\s*\|", stripped)):
            continue
        cells = [c.strip() for c in stripped.split("|")[1:-1]]
        if len(cells) >= 2:
            field = cells[1].strip("`")
            if field:
                fields.append(field)
    return fields


def test_requirements_matrix_exists_and_passes_traceability_gate() -> None:
    text = _matrix_text()
    errors: list[str] = []
    errors.extend(_canonical_ref_errors(text))
    errors.extend(_ac_coverage_errors(text))
    for forbidden in _FORBIDDEN_IN_MATRIX:
        if forbidden in text:
            errors.append(f"la matriz referencia una tarea o campo prohibido: {forbidden}")
    assert not errors, "violaciones de trazabilidad:\n- " + "\n- ".join(errors)


def test_all_test_references_are_canonical_and_resolvable() -> None:
    text = _matrix_text()
    refs = _collect_references(text)
    assert refs, "no se encontraron referencias de prueba en la matriz"
    errors = _canonical_ref_errors(text)
    assert not errors, "referencias no canónicas:\n- " + "\n- ".join(errors)


def test_all_acceptance_criteria_1_to_18_present() -> None:
    errors = _ac_coverage_errors(_matrix_text())
    assert not errors, "AC sin cobertura: " + ", ".join(errors)


def test_no_reference_to_follow_up_tasks() -> None:
    text = _matrix_text()
    for forbidden in ("H3.3.7", "H3.3.8", "H3.2"):
        assert forbidden not in text, f"la matriz referencia una tarea posterior: {forbidden}"


def test_columns_allowlist_matches_implementation_exactly() -> None:
    fields = _allowlist_fields(_columns_text())
    assert fields == _EXPECTED_FIELDS, (
        f"allowlist distinta de la esperada (orden incluido):\n"
        f"esperada={_EXPECTED_FIELDS}\nactual={fields}"
    )


def test_columns_doc_explicitly_excludes_raw_payload_and_secrets() -> None:
    text = _columns_text()
    assert "raw_payload" in text, "la matriz de columnas no excluye explícitamente raw_payload"
    assert "password_hash" in text, "la matriz de columnas no excluye password_hash"
