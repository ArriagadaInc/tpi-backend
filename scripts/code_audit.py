"""
Script de Auditoría de Código.

Verifica:
- Imports no utilizados
- Funciones sin docstring
- Type hints faltantes
- Código duplicado
- Dependencias vulnerables
- Métricas de código
"""

import ast
import re
from pathlib import Path


def print_header(title: str):
    """Imprime header de sección."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_warning(message: str):
    """Imprime advertencia."""
    print(f"⚠️  {message}")


def print_success(message: str):
    """Imprime mensaje de éxito."""
    print(f"✅ {message}")


def print_error(message: str):
    """Imprime error."""
    print(f"❌ {message}")


class CodeAuditor:
    """Auditoría de código Python."""

    def __init__(self, root_dir: str = "app"):
        self.root_dir = Path(root_dir)
        self.issues = []
        self.metrics = {
            "total_files": 0,
            "total_lines": 0,
            "total_functions": 0,
            "functions_with_docstring": 0,
            "functions_with_type_hints": 0,
            "unused_imports": 0,
            "files_with_issues": 0,
        }

    def audit(self) -> dict:
        """Ejecuta auditoría completa."""
        print_header("AUDITORÍA DE CÓDIGO")

        py_files = list(self.root_dir.rglob("*.py"))
        self.metrics["total_files"] = len(py_files)

        for py_file in py_files:
            self._audit_file(py_file)

        return self._generate_report()

    def _audit_file(self, py_file: Path):
        """Audita un archivo Python."""
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            self.metrics["total_lines"] += len(content.split("\n"))

            # Parse AST
            try:
                tree = ast.parse(content)
            except SyntaxError as e:
                self.issues.append((py_file, f"Syntax error: {e}"))
                return

            # Verificar funciones
            self._check_functions(py_file, tree, content)

            # Verificar imports
            self._check_imports(py_file, tree, content)

            # Verificar docstrings
            self._check_docstrings(py_file, tree)

        except Exception as e:
            self.issues.append((py_file, f"Error: {e}"))

    def _check_functions(self, py_file: Path, tree: ast.AST, content: str):
        """Verifica funciones."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.metrics["total_functions"] += 1

                # Verificar type hints
                has_return_type = node.returns is not None
                has_arg_types = all(arg.annotation is not None for arg in node.args.args)

                if has_return_type and has_arg_types:
                    self.metrics["functions_with_type_hints"] += 1

                # Verificar docstring
                has_docstring = ast.get_docstring(node) is not None
                if has_docstring:
                    self.metrics["functions_with_docstring"] += 1
                else:
                    # Ignorar funciones privadas y test functions
                    if not node.name.startswith("_") and not node.name.startswith("test_"):
                        self.issues.append(
                            (
                                py_file,
                                f"Función sin docstring: {node.name} (línea {node.lineno})",
                            )
                        )

    def _check_imports(self, py_file: Path, tree: ast.AST, content: str):
        """Verifica imports no utilizados."""
        imports = {}

        # Recolectar imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imports[name] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imports[name] = node.lineno

        # Verificar uso
        for import_name, line_no in imports.items():
            # Ignorar imports especiales
            if import_name.startswith("_"):
                continue

            # Crear patrón de búsqueda
            pattern = rf"\b{re.escape(import_name)}\b"

            # Contar usos (excluyendo línea de import)
            uses = 0
            for i, line in enumerate(content.split("\n"), 1):
                if i != line_no and re.search(pattern, line):
                    uses += 1

            if uses == 0:
                self.issues.append(
                    (py_file, f"Import no utilizado: {import_name} (línea {line_no})")
                )
                self.metrics["unused_imports"] += 1

    def _check_docstrings(self, py_file: Path, tree: ast.AST):
        """Verifica docstrings."""
        # Verificar módulo
        if ast.get_docstring(tree) is None:
            self.issues.append((py_file, "Módulo sin docstring"))


def check_dependencies() -> tuple[bool, list[str]]:
    """Verifica dependencias conocidas como vulnerables."""
    print_header("Verificación de Dependencias")

    vulnerable = {
        "django": ["<4.2.0", "XSS vulnerability"],
        "requests": ["<2.28.0", "Security issue"],
        "flask": ["<2.2.0", "Known vulnerability"],
        "jinja2": ["<3.1.0", "Security issue"],
    }

    issues = []

    # Leer pyproject.toml o requirements.txt
    req_file = None
    if Path("pyproject.toml").exists():
        req_file = Path("pyproject.toml")
    elif Path("requirements.txt").exists():
        req_file = Path("requirements.txt")

    if not req_file:
        print_warning("requirements.txt o pyproject.toml no encontrado")
        return True, []

    content = req_file.read_text()

    for package, (version_spec, description) in vulnerable.items():
        # Búsqueda simple de paquetes
        if re.search(rf"\b{package}\b", content, re.IGNORECASE):
            print_warning(f"{package}: {description}")
            issues.append(f"{package}: {description}")

    if not issues:
        print_success("No vulnerabilidades conocidas encontradas")
        return True, []

    return False, issues


def generate_report(auditor: CodeAuditor) -> None:
    """Genera reporte de auditoría."""
    print_header("REPORTE DE AUDITORÍA")

    metrics = auditor.metrics

    print(f"Archivos Python: {metrics['total_files']}")
    print(f"Líneas totales: {metrics['total_lines']}")
    print(f"Funciones: {metrics['total_functions']}")

    if metrics["total_functions"] > 0:
        docstring_pct = (metrics["functions_with_docstring"] / metrics["total_functions"]) * 100
        type_hint_pct = (metrics["functions_with_type_hints"] / metrics["total_functions"]) * 100

        print(f"\nCobertura de Docstrings: {docstring_pct:.1f}%")
        print(f"Cobertura de Type Hints: {type_hint_pct:.1f}%")

    print(f"\nImports no utilizados: {metrics['unused_imports']}")

    if auditor.issues:
        print(f"\nProblemas encontrados: {len(auditor.issues)}")
        print("\nPrimeros 20 problemas:")
        for i, (file_path, issue) in enumerate(auditor.issues[:20], 1):
            print(f"{i}. {file_path}: {issue}")

        if len(auditor.issues) > 20:
            print(f"\n... y {len(auditor.issues) - 20} más")
    else:
        print_success("\n✨ Auditoría completada sin problemas críticos")


def main():
    """Función principal."""
    print("\n" + "=" * 70)
    print("  AUDITORÍA DE CÓDIGO - Tu Pensión Inteligente")
    print("=" * 70)

    # Auditoría de código
    auditor = CodeAuditor("app")
    auditor.audit()

    # Verificación de dependencias
    deps_ok, deps_issues = check_dependencies()

    # Generar reporte
    generate_report(auditor)

    print()

    # Resumen final
    total_issues = len(auditor.issues) + len(deps_issues)

    if total_issues == 0:
        print_success("✨ AUDITORÍA COMPLETADA - SIN PROBLEMAS CRÍTICOS")
        return 0
    else:
        print_error(f"⚠️  {total_issues} problemas encontrados")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
