"""Script para generar y verificar la estructura del proyecto."""

import os
from pathlib import Path
from typing import List, Tuple

# Directorios y archivos esperados
PROJECT_STRUCTURE = {
    "app": {
        "config": ["__init__.py", "settings.py"],
        "database": ["__init__.py", "connection.py", "healthcheck.py"],
        "validators": ["__init__.py", "rut.py", "phone.py", "email.py"],
        "models": ["__init__.py", "solicitud.py"],
        "security": ["__init__.py", "masking.py"],
        "services": ["__init__.py", "solicitud_service.py"],
        "repositories": ["__init__.py", "solicitud_repository.py"],
        "pages": ["__init__.py"],
        "components": ["__init__.py"],
    },
    "tests": {
        "unit": ["__init__.py", "test_rut.py", "test_phone.py", "test_email.py"],
        "integration": ["__init__.py", "test_solicitud_flow.py"],
    },
    "scripts": ["__init__.py", "verify_database_connection.py"],
    "root_files": [
        "pyproject.toml",
        ".env.example",
        ".env",
        ".gitignore",
        "README.md",
    ],
}


def check_structure(root_path: Path) -> Tuple[bool, List[str]]:
    """
    Verifica que la estructura del proyecto sea correcta.

    Args:
        root_path: Ruta raíz del proyecto

    Returns:
        Tupla (todas_correctas, lista_de_errores)
    """
    errors = []

    # Verificar directorios y archivos anidados
    for dir_name, contents in PROJECT_STRUCTURE.items():
        if dir_name == "root_files":
            for file_name in contents:
                file_path = root_path / file_name
                if not file_path.exists():
                    errors.append(f"❌ Falta archivo raíz: {file_name}")
        else:
            dir_path = root_path / dir_name
            if not dir_path.exists():
                errors.append(f"❌ Falta directorio: {dir_name}")
                continue

            for subdir_name, files in contents.items():
                if isinstance(files, list):
                    # Verificar subdirectorio
                    subdir_path = dir_path / subdir_name
                    if not subdir_path.exists():
                        errors.append(f"❌ Falta subdirectorio: {dir_name}/{subdir_name}")
                        continue

                    # Verificar archivos en subdirectorio
                    for file_name in files:
                        file_path = subdir_path / file_name
                        if not file_path.exists():
                            errors.append(
                                f"❌ Falta archivo: {dir_name}/{subdir_name}/{file_name}"
                            )
                else:
                    # Verificar archivos en directorio principal
                    file_path = dir_path / subdir_name
                    if not file_path.exists():
                        errors.append(f"❌ Falta archivo: {dir_name}/{subdir_name}")

    return len(errors) == 0, errors


def print_tree(root_path: Path, prefix: str = "", is_last: bool = True) -> None:
    """Imprime un árbol visual de la estructura."""
    print(f"{prefix}{'└── ' if is_last else '├── '}{root_path.name}/")

    # Directorios de interés
    dirs_to_show = [
        "app",
        "tests",
        "scripts",
    ]
    files_to_show = [
        "pyproject.toml",
        ".env.example",
        ".gitignore",
        "README.md",
    ]

    try:
        contents = list(root_path.iterdir())
        contents.sort(key=lambda x: (not x.is_dir(), x.name))

        # Filtrar directorios
        dirs = [c for c in contents if c.is_dir() and c.name in dirs_to_show]
        files = [c for c in contents if c.is_file() and c.name in files_to_show]

        all_items = dirs + files

        for i, item in enumerate(all_items):
            is_last_item = i == len(all_items) - 1
            new_prefix = prefix + ("    " if is_last else "│   ")

            if item.is_dir():
                print(
                    f"{new_prefix}{'└── ' if is_last_item else '├── '}{item.name}/"
                )
                print_dir_contents(item, new_prefix, is_last_item)
            else:
                print(f"{new_prefix}{'└── ' if is_last_item else '├── '}{item.name}")
    except PermissionError:
        print(f"{prefix}[Permiso denegado]")


def print_dir_contents(
    dir_path: Path, prefix: str = "", parent_is_last: bool = True
) -> None:
    """Imprime el contenido de un directorio."""
    try:
        contents = list(dir_path.iterdir())
        contents.sort(key=lambda x: (not x.is_dir(), x.name))

        # Excluir directorios de build y cache
        exclude_dirs = {".pytest_cache", "__pycache__", ".venv", "build", "dist"}
        contents = [c for c in contents if c.name not in exclude_dirs]

        for i, item in enumerate(contents):
            is_last = i == len(contents) - 1
            new_prefix = prefix + ("    " if parent_is_last else "│   ")

            if item.is_dir():
                print(f"{new_prefix}{'└── ' if is_last else '├── '}{item.name}/")
            else:
                print(f"{new_prefix}{'└── ' if is_last else '├── '}{item.name}")
    except PermissionError:
        pass


def main():
    """Función principal."""
    project_root = Path(__file__).parent.parent

    print("=" * 80)
    print("TU PENSIÓN INTELIGENTE - VERIFICACIÓN DE ESTRUCTURA")
    print("=" * 80)
    print()

    # Verificar estructura
    all_correct, errors = check_structure(project_root)

    if all_correct:
        print("✅ ESTRUCTURA DEL PROYECTO VERIFICADA CORRECTAMENTE")
    else:
        print("❌ PROBLEMAS DETECTADOS:")
        for error in errors:
            print(f"  {error}")

    print()
    print("ÁRBOL DEL PROYECTO:")
    print("=" * 80)
    print_tree(project_root)

    print()
    print("=" * 80)
    print("ESTADÍSTICAS:")
    print("=" * 80)

    # Contar archivos Python
    py_files = list(project_root.rglob("*.py"))
    py_files = [
        f
        for f in py_files
        if ".venv" not in str(f) and ".pytest_cache" not in str(f)
    ]
    print(f"Archivos Python: {len(py_files)}")

    # Contar líneas de código
    total_lines = 0
    for py_file in py_files:
        try:
            with open(py_file) as f:
                total_lines += len(f.readlines())
        except Exception:
            pass
    print(f"Líneas de código: {total_lines:,}")

    # Verificar dependencias
    requirements_file = project_root / "pyproject.toml"
    if requirements_file.exists():
        print(f"Archivo de dependencias: ✅ pyproject.toml")
    else:
        print(f"Archivo de dependencias: ❌ NO ENCONTRADO")

    # Verificar configuración
    env_example = project_root / ".env.example"
    env_file = project_root / ".env"
    print(f"Configuración: .env.example {'✅' if env_example.exists() else '❌'}")
    print(f"Configuración: .env {'✅' if env_file.exists() else '❌'}")

    print()
    return 0 if all_correct else 1


if __name__ == "__main__":
    exit(main())
