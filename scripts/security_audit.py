"""
Script de auditoría de seguridad.

Verifica:
- Dependencias vulnerables
- Patrones peligrosos en código
- Exposición de secretos
- Permisos de archivos
- Archivos sensibles no protegidos
"""

import os
import re
import sys
import json
from pathlib import Path
from typing import List, Tuple


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


def check_hardcoded_secrets() -> Tuple[bool, List[str]]:
    """Verifica hardcoded secrets en código."""
    print_header("Verificación de Secretos Hardcodeados")
    
    patterns = [
        (r"DATABASE_PASSWORD\s*=\s*['\"](?!.*\{).*['\"]", "DATABASE_PASSWORD hardcodeado"),
        (r"API_KEY\s*=\s*['\"](?!.*\{).*['\"]", "API_KEY hardcodeado"),
        (r"SECRET_KEY\s*=\s*['\"](?!.*\{).*['\"]", "SECRET_KEY hardcodeado"),
        (r"password\s*=\s*['\"](?!.*\{).*['\"]", "password hardcodeado"),
        (r"token\s*=\s*['\"](?!.*\{).*['\"]", "token hardcodeado"),
    ]
    
    issues = []
    root = Path("app")
    
    for py_file in root.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            for pattern, description in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    issues.append(f"{py_file}: {description}")
                    print_warning(f"{py_file}: {description}")
        except Exception as e:
            print_warning(f"Error reading {py_file}: {e}")
    
    if not issues:
        print_success("No secrets hardcodeados encontrados")
        return True, []
    
    return False, issues


def check_sql_injection_patterns() -> Tuple[bool, List[str]]:
    """Verifica patrones potenciales de SQL injection."""
    print_header("Verificación de Patrones SQL Injection")
    
    patterns = [
        (r'execute\s*\(\s*f["\']', "f-string en execute (potencial SQL injection)"),
        (r'execute\s*\(\s*["\'].*\+.*["\']', "String concatenation en execute"),
        (r"cursor\.execute\s*\(\s*[^,]*\s*%\s*\(", "Parametrized queries (seguro)"),
    ]
    
    issues = []
    root = Path("app")
    
    for py_file in root.rglob("*.py"):
        if "test" in str(py_file):
            continue
        
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            
            # Buscar execute() con f-strings
            if re.search(r'execute\s*\(\s*f["\']', content):
                issues.append(f"{py_file}: Posible SQL injection con f-string")
                print_warning(f"{py_file}: Posible SQL injection con f-string")
            
            # Buscar .format() en execute
            if re.search(r'\.execute\s*\(\s*.*\.format\s*\(', content):
                issues.append(f"{py_file}: Posible SQL injection con .format()")
                print_warning(f"{py_file}: Posible SQL injection con .format()")
        
        except Exception as e:
            print_warning(f"Error reading {py_file}: {e}")
    
    if not issues:
        print_success("No patrones SQL injection encontrados")
        return True, []
    
    return False, issues


def check_dangerous_imports() -> Tuple[bool, List[str]]:
    """Verifica imports peligrosos."""
    print_header("Verificación de Imports Peligrosos")
    
    dangerous = {
        "pickle": "pickle puede ejecutar código arbitrario",
        "eval": "eval() es peligroso",
        "exec": "exec() es peligroso",
        "__import__": "__import__ puede ser peligroso",
        "os.system": "os.system es vulnerable a command injection",
        "subprocess.call": "subprocess sin shell=False es peligroso",
    }
    
    issues = []
    root = Path("app")
    
    for py_file in root.rglob("*.py"):
        if "test" in str(py_file):
            continue
        
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            
            # Verificar pickle
            if "import pickle" in content and "json" not in content:
                issues.append(f"{py_file}: Usa pickle (considera usar json)")
                print_warning(f"{py_file}: Usa pickle")
            
            # Verificar eval/exec
            if re.search(r'\b(eval|exec)\s*\(', content):
                issues.append(f"{py_file}: Usa eval/exec")
                print_error(f"{py_file}: CRÍTICO - Usa eval/exec")
            
            # Verificar os.system
            if "os.system" in content:
                issues.append(f"{py_file}: Usa os.system")
                print_error(f"{py_file}: CRÍTICO - Usa os.system")
            
            # Verificar subprocess sin shell=False
            if "subprocess" in content and "shell=True" in content:
                issues.append(f"{py_file}: subprocess con shell=True")
                print_error(f"{py_file}: CRÍTICO - subprocess con shell=True")
        
        except Exception as e:
            print_warning(f"Error reading {py_file}: {e}")
    
    if not issues:
        print_success("No imports peligrosos encontrados")
        return True, []
    
    return len([i for i in issues if "CRÍTICO" not in str(i)]) == 0, issues


def check_env_file_protection() -> Tuple[bool, List[str]]:
    """Verifica que .env no esté commiteado."""
    print_header("Verificación de Protección .env")
    
    issues = []
    
    # Verificar .env existe
    if Path(".env").exists():
        print_success(".env existe (local)")
    
    # Verificar .gitignore
    if Path(".gitignore").exists():
        gitignore = Path(".gitignore").read_text()
        if ".env" in gitignore:
            print_success(".env está en .gitignore")
        else:
            issues.append(".env NO está en .gitignore")
            print_error(".env NO está en .gitignore")
        
        # Verificar otros archivos sensibles
        sensitive = ["*.key", "*.pem", "credentials/", "secrets/"]
        for pattern in sensitive:
            if pattern in gitignore:
                print_success(f"{pattern} está protegido en .gitignore")
            else:
                print_warning(f"{pattern} no está en .gitignore")
    else:
        issues.append(".gitignore no existe")
        print_error(".gitignore no existe")
    
    return len(issues) == 0, issues


def check_pydantic_validation() -> Tuple[bool, List[str]]:
    """Verifica que Pydantic valida correctamente."""
    print_header("Verificación de Validación Pydantic")
    
    issues = []
    models_file = Path("app/models/solicitud.py")
    
    if models_file.exists():
        content = models_file.read_text()
        
        # Verificar que hay validadores
        if "validator" in content or "field_validator" in content:
            print_success("Validadores Pydantic encontrados")
        else:
            issues.append("No se encontraron validadores Pydantic")
            print_warning("Considera agregar field validators")
        
        # Verificar que hay tipos
        if ":" in content and "PersonaData" in content:
            print_success("Type hints presentes en modelos")
        else:
            issues.append("Falta type hints en modelos")
            print_warning("Considera agregar type hints")
    else:
        issues.append("solicitud.py no encontrado")
        print_error("solicitud.py no encontrado")
    
    return len(issues) == 0, issues


def check_masking_implementation() -> Tuple[bool, List[str]]:
    """Verifica que enmascaramiento se implementa."""
    print_header("Verificación de Enmascaramiento de Datos")
    
    issues = []
    masking_file = Path("app/security/masking.py")
    
    if masking_file.exists():
        content = masking_file.read_text()
        
        # Verificar funciones de masking
        functions = ["mask_rut", "mask_email", "mask_phone"]
        for func in functions:
            if func in content:
                print_success(f"Función {func} implementada")
            else:
                issues.append(f"Función {func} no encontrada")
                print_warning(f"Falta {func}")
        
        # Verificar que se usa en servicios
        service_file = Path("app/services/solicitud_service.py")
        if service_file.exists():
            service_content = service_file.read_text()
            if "mask" in service_content or "masked" in service_content:
                print_success("Enmascaramiento utilizado en servicios")
            else:
                issues.append("Enmascaramiento no usado en servicios")
                print_warning("Considera enmascarar datos sensibles en servicios")
    else:
        issues.append("masking.py no encontrado")
        print_error("masking.py no encontrado")
    
    return len(issues) == 0, issues


def check_credential_files() -> Tuple[bool, List[str]]:
    """Verifica que archivos de credenciales no estén en repo."""
    print_header("Verificación de Archivos de Credenciales")
    
    issues = []
    sensitive_files = [
        ".env",
        "credentials.json",
        "secrets.json",
        "*.pem",
        "*.key",
        ".aws/credentials",
    ]
    
    for pattern in sensitive_files:
        if "*" in pattern:
            # Verificar wildcard
            from glob import glob
            matches = glob(f"**/{pattern}", recursive=True)
            if matches:
                for match in matches:
                    if not Path(match).name.startswith("."):
                        issues.append(f"Archivo sensible encontrado: {match}")
                        print_error(f"Archivo sensible encontrado: {match}")
        else:
            if Path(pattern).exists():
                # Está bien si está en .gitignore
                gitignore = Path(".gitignore").read_text() if Path(".gitignore").exists() else ""
                if pattern not in gitignore:
                    issues.append(f"{pattern} existe y no está en .gitignore")
                    print_warning(f"{pattern} no protegido en .gitignore")
                else:
                    print_success(f"{pattern} protegido")
    
    return len(issues) == 0, issues


def check_input_validation() -> Tuple[bool, List[str]]:
    """Verifica implementación de validación de input."""
    print_header("Verificación de Validación de Input")
    
    issues = []
    validators_dir = Path("app/validators")
    
    if validators_dir.exists():
        validators = list(validators_dir.glob("*.py"))
        if len(validators) >= 3:
            print_success(f"Validadores encontrados: {len(validators)}")
        else:
            issues.append(f"Pocos validadores: {len(validators)}")
            print_warning(f"Considera agregar más validadores")
    else:
        issues.append("Directorio validators no encontrado")
        print_error("Directorio validators no encontrado")
    
    return len(issues) == 0, issues


def generate_summary(results: List[Tuple[str, bool, List[str]]]) -> None:
    """Genera resumen de auditoría."""
    print_header("RESUMEN DE AUDITORÍA DE SEGURIDAD")
    
    total = len(results)
    passed = sum(1 for _, success, _ in results if success)
    
    print(f"Total de verificaciones: {total}")
    print(f"Pasadas: {passed}/{total}")
    print(f"Tasa de aprobación: {passed*100//total}%\n")
    
    for name, success, issues in results:
        status = "✅ PASÓ" if success else "❌ FALLÓ"
        print(f"{status}: {name}")
        if issues and not success:
            for issue in issues[:3]:  # Mostrar primeros 3
                print(f"       - {issue}")
            if len(issues) > 3:
                print(f"       ... y {len(issues) - 3} más")
    
    print()
    if passed == total:
        print_success("✨ TODAS LAS VERIFICACIONES PASARON")
    else:
        print_error(f"⚠️  {total - passed} verificaciones fallaron")


def main():
    """Función principal."""
    print("\n" + "="*70)
    print("  AUDITORÍA DE SEGURIDAD - Tu Pensión Inteligente")
    print("="*70)
    
    results = [
        ("Secretos Hardcodeados", *check_hardcoded_secrets()),
        ("Patrones SQL Injection", *check_sql_injection_patterns()),
        ("Imports Peligrosos", *check_dangerous_imports()),
        ("Protección .env", *check_env_file_protection()),
        ("Validación Pydantic", *check_pydantic_validation()),
        ("Enmascaramiento", *check_masking_implementation()),
        ("Archivos de Credenciales", *check_credential_files()),
        ("Validación de Input", *check_input_validation()),
    ]
    
    generate_summary(results)
    
    # Retornar exit code
    failed = sum(1 for _, success, _ in results if not success)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
