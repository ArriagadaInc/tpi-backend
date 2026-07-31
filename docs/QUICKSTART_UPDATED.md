# GUÍA RÁPIDA - ETAPA 5 ✅

Instrucciones paso a paso para instalar, verificar y ejecutar la aplicación completa.

---

## 📋 Tabla de Contenidos

1. [Instalación Rápida (5 min)](#instalación-rápida-5-min)
2. [Ejecución de la Aplicación](#ejecución-de-la-aplicación)
3. [Ejecución de Tests](#ejecución-de-tests)
4. [Troubleshooting Completo](#troubleshooting-completo)
5. [Comandos Útiles](#comandos-útiles)
6. [Validación Completa](#validación-completa)

---

## 🚀 Instalación Rápida (5 min)

### Paso 1: Configuración Inicial

```bash
# Navegar al directorio
cd c:\desarrollos\tu-pension-inteligente-backoffice

# Crear entorno virtual
python -m venv .venv

# Activar entorno
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Windows CMD:
.venv\Scripts\activate.bat
# Linux/Mac:
source .venv/bin/activate
```

### Paso 2: Instalar Dependencias

```bash
# Instalar todo (incluye Streamlit, DB, testing, dev tools)
pip install -e ".[dev]"

# Verificar instalación
pip list | grep -E "streamlit|psycopg|pydantic|pytest"
```

### Paso 3: Configurar BD

```bash
# Asegurar que .env existe con credenciales correctas
# (Ya debe haber un .env local con config)

# Editar .env si es necesario
# Requeridas:
# DATABASE_HOST=localhost
# DATABASE_PORT=5432
# DATABASE_NAME=tpi_local
# DATABASE_USER=tpi_app
# DATABASE_PASSWORD=<tu_contraseña>
# DATABASE_SCHEMA=tpi
```

### Paso 4: Verificar Conexión

```bash
# Verificar que BD está disponible
python scripts/verify_database_connection.py

# Resultado esperado:
# ✅ TODAS LAS VERIFICACIONES PASARON CORRECTAMENTE
```

### ✅ Listo para Usar

La instalación está completa. Procede a la siguiente sección.

---

## 🎯 Ejecución de la Aplicación

### Opción 1: Streamlit App (Interfaz Web)

```bash
# Iniciar aplicación Streamlit
streamlit run app/streamlit_app.py

# Se abrirá automáticamente en:
# http://localhost:8501
```

**Navegación:**
- **Página Principal**: Dashboard con estadísticas
- **Registrar Solicitud**: Formulario para nuevas solicitudes
- **Solicitudes Registradas**: Búsqueda y consulta
- **Trazabilidad**: Métricas y análisis

### Opción 2: Verificación de Scripts

```bash
# Auditoría de seguridad
python scripts/security_audit.py

# Verificar estructura
python scripts/verify_project_structure.py

# Verificar BD
python scripts/verify_database_connection.py
```

---

## 🧪 Ejecución de Tests

### Tests Unitarios (Rápido, ~30s)

```bash
# Todos los unitarios
pytest tests/unit/ -v

# Tests específicos
pytest tests/unit/test_rut.py -v
pytest tests/unit/test_email.py -v
pytest tests/unit/test_phone.py -v
```

### Tests de Integración (Más lento, ~1m)

```bash
# Todos los de integración (requieren BD)
pytest tests/integration/ -v

# Con detalle de error
pytest tests/integration/ -vv --tb=long
```

### Tests E2E de Streamlit (Etapa 4)

```bash
# Validar que páginas se cargan correctamente
pytest tests/e2e/ -v

# Tests específicos
pytest tests/e2e/test_streamlit_app.py -v
pytest tests/e2e/test_registro_solicitud.py -v
pytest tests/e2e/test_consulta_solicitudes.py -v
pytest tests/e2e/test_trazabilidad.py -v
```

### Tests de Seguridad

```bash
# Validar prevención de ataques
pytest tests/security/ -v

# Tests específicos
pytest tests/security/test_security.py::TestSQLInjectionPrevention -v
pytest tests/security/test_security.py::TestXSSPrevention -v
pytest tests/security/test_security.py::TestInputValidationRobustness -v
```

### Todos los Tests + Cobertura

```bash
# Ejecutar todo con reporte de cobertura
pytest --cov=app --cov-report=html

# Abrir reporte (Windows)
start htmlcov/index.html
# (Linux/Mac)
open htmlcov/index.html

# Ver resumen en consola
pytest --cov=app --cov-report=term-missing
```

### Ejecución Rápida (Sin paralelo)

```bash
# Si hay problemas de memoria/puerto
pytest -n 1 --tb=short

# Un módulo a la vez
pytest tests/unit/ && pytest tests/integration/ && pytest tests/e2e/
```

---

## 🆘 Troubleshooting Completo

### Problemas de Instalación

#### "No module named 'app'"

```bash
# Causa: Python no encuentra el módulo app

# Solución 1: Reinstalar en modo editable
pip install -e ".[dev]"

# Solución 2: Agregar ruta al PYTHONPATH
# Windows PowerShell:
$env:PYTHONPATH = "$PWD;$env:PYTHONPATH"

# Windows CMD:
set PYTHONPATH=%CD%;%PYTHONPATH%

# Linux/Mac:
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

#### "ModuleNotFoundError: No module named 'streamlit'"

```bash
# Causa: Streamlit no instalado

# Solución: Instalar dev dependencies
pip install -e ".[dev]"

# Verificar instalación
python -c "import streamlit; print(streamlit.__version__)"
```

#### "ModuleNotFoundError: No module named 'psycopg'"

```bash
# Causa: Driver de PostgreSQL no instalado

# Solución: Instalar psycopg3 con soporte binario
pip install psycopg[binary]>=3.1.0

# Alternativa: Reinstalar todo
pip uninstall psycopg -y
pip install -e ".[dev]"

# Verificar
python -c "import psycopg; print(psycopg.__version__)"
```

#### "ModuleNotFoundError: No module named 'pydantic'"

```bash
# Causa: Pydantic no instalado o versión incorrecta

# Solución: Actualizar Pydantic
pip install --upgrade pydantic>=2.0.0 pydantic-settings>=2.0.0

# Verificar
python -c "from pydantic import BaseModel; print('OK')"
```

#### "Version Conflict" en dependencias

```bash
# Causa: Versiones incompatibles instaladas

# Solución: Limpiar e reinstalar
pip uninstall -y streamlit psycopg pydantic pytest
pip install -e ".[dev]"

# Verificar all versiones
pip check
```

### Problemas de Base de Datos

#### "Connection refused" a PostgreSQL

```bash
# Verificar que PostgreSQL está corriendo

# Windows:
# 1. Abrir Services (services.msc)
# 2. Buscar "PostgreSQL"
# 3. Si está stopped, dar click derecho > Start

# Linux:
sudo systemctl start postgresql
sudo systemctl status postgresql

# Mac:
brew services start postgresql
```

#### "FATAL: Ident authentication failed"

```bash
# Causa: BD requiere autenticación pero .env tiene credenciales incorrectas

# Solución: Verificar credenciales en .env
cat .env | grep DATABASE_

# Verificar conexión directa
psql -h localhost -U tpi_app -d tpi_local -c "SELECT 1"

# Si pide contraseña y no recuerdas:
# (Linux - resetear contraseña)
sudo -u postgres psql
\password tpi_app
# Ingresa contraseña nueva
# \q para salir
```

#### "Database does not exist"

```bash
# Causa: Base de datos no creada o credenciales apuntan a DB equivocada

# Solución 1: Crear desde proyecto tpi-data-pipeline
cd ../tpi-data-pipeline
.venv/Scripts/Activate.ps1  # Activar su venv
python setup_db.py
cd ../tu-pension-inteligente-backoffice

# Solución 2: Verificar que credenciales son correctas
cat .env | grep DATABASE_NAME  # Debe ser tpi_local

# Solución 3: Crear manualmente
psql -U postgres
CREATE DATABASE tpi_local;
\q
```

#### "Relation 'tpi.personas' does not exist"

```bash
# Causa: Esquema o tablas no creadas

# Solución: Ejecutar setup desde tpi-data-pipeline
cd ../tpi-data-pipeline
python setup_db.py

# Verificar tablas
psql tpi_local -c "\dt tpi.*"  # Debe mostrar personas, leads, consentimientos, etc
```

#### "Too many connections"

```bash
# Causa: Connection pool agotado

# Solución: Reiniciar aplicación o PostgreSQL
# Streamlit:
# 1. Ctrl+C en terminal
# 2. streamlit run app/streamlit_app.py

# PostgreSQL:
sudo systemctl restart postgresql  # Linux
brew services restart postgresql   # Mac
```

#### "Disk I/O error"

```bash
# Causa: Espacio en disco o error hardware

# Solución: Verificar espacio
df -h  # Linux/Mac
Get-Volume  # Windows

# Si el disco está lleno, liberar espacio y reintentar
```

### Problemas de Streamlit

#### "Address already in use"

```bash
# Causa: Puerto 8501 ya está en uso

# Solución 1: Usar puerto diferente
streamlit run app/streamlit_app.py --server.port 8502

# Solución 2: Matar el proceso anterior
# Windows:
netstat -ano | findstr 8501
taskkill /PID <PID> /F

# Linux/Mac:
lsof -ti:8501 | xargs kill -9
```

#### "Cache folder does not exist"

```bash
# Causa: Carpeta de cache corrupida

# Solución: Limpiar cache
rm -rf ~/.streamlit/cache  # Linux/Mac
rmdir /S %AppData%\.streamlit\cache  # Windows

# Reintentar
streamlit run app/streamlit_app.py
```

#### "RuntimeError: could not connect to server"

```bash
# Causa: BD no disponible cuando inicia Streamlit

# Solución 1: Verificar BD
python scripts/verify_database_connection.py

# Solución 2: Si BD está OK, revisar logs
tail -f logs/backoffice.log

# Solución 3: Ver error completo
streamlit run app/streamlit_app.py --logger.level=debug
```

#### "AttributeError: 'NoneType' object"

```bash
# Causa: Streamlit component está retornando None

# Solución: Revisar session_state
# En app/pages/2_solicitudes_registradas.py, línea X:
if "current_page" not in st.session_state:
    st.session_state.current_page = 1
```

### Problemas de Tests

#### "pytest: command not found"

```bash
# Causa: pytest no instalado

# Solución: Instalar dev dependencies
pip install -e ".[dev]"

# O instalar pytest directamente
pip install pytest>=7.4.0 pytest-cov>=4.1.0
```

#### "FAILED tests/integration/..."

```bash
# Causa: Test requiere BD y algo falla

# Solución 1: Verificar BD
python scripts/verify_database_connection.py

# Solución 2: Ver error detallado
pytest tests/integration/test_solicitud_flow.py -vv --tb=long

# Solución 3: Limpiar datos de prueba anterior
# (Si hay tabla llena, eso puede afectar)
# Ver datos:
psql tpi_local -c "SELECT COUNT(*) FROM tpi.leads"
```

#### "FAILED tests/e2e/..."

```bash
# Causa: AppTest no funciona correctamente

# Solución 1: Asegurar Streamlit >= 1.28.0
pip install --upgrade streamlit

# Solución 2: Ver si el módulo está disponible
python -c "from streamlit.testing.v1 import AppTest; print('OK')"

# Solución 3: Ejecutar con más verbosidad
pytest tests/e2e/test_streamlit_app.py -vv --tb=short
```

#### "Cobertura muy baja"

```bash
# Causa: No todos los archivos se están probando

# Solución: Ver qué líneas no están cubiertas
pytest --cov=app --cov-report=term-missing

# Agregar tests para archivo específico
pytest --cov=app.validators --cov-report=term-missing
```

#### "Test times out"

```bash
# Causa: Test tarda demasiado

# Solución 1: Aumentar timeout
pytest --timeout=300  # 5 minutos

# Solución 2: Ejecutar sin paralelismo
pytest -n 1

# Solución 3: Identificar test lento
pytest -v --durations=10
```

### Problemas de Validación

#### "RUT validation failed: Invalid check digit"

```bash
# Causa: Dígito verificador incorrecto

# Verificar RUT con módulo 11:
# RUT 12345678-5
# Cálculo: 1×2 + 2×3 + 3×4 + 4×5 + 5×6 + 6×7 + 7×2 + 8×3 = ?
# suma % 11 = ?
# 11 - (suma % 11) = dígito

# Ver tests
pytest tests/unit/test_rut.py::TestValidateRut -v

# RUTs válidos para prueba:
# 12345678-5 ✓
# 1-9 ✓
# 24052344-8 ✓
```

#### "Email validation failed: Invalid format"

```bash
# Causa: Formato de email incorrecto

# Inválidos:
# juan @example.com (espacio)
# juan@example (sin extensión)
# juan@.com (sin dominio)
# juan@@example.com (doble @)

# Válidos:
# juan@example.com ✓
# juan.perez@example.co.uk ✓
# juan+tag@example.com ✓

# Ver tests
pytest tests/unit/test_email.py::TestValidateEmail -v
```

#### "Phone validation failed: Invalid format"

```bash
# Causa: Formato de teléfono incorrecto

# Debe ser celular chileno formato +56

# Inválidos:
# +55912345678 (código país incorrecto)
# 02 1234 5678 (fijo, no celular)
# 812345678 (sin código país)

# Válidos:
# +56912345678 ✓
# 09 1234 5678 ✓ (normalizado)
# 912345678 ✓ (convertido)

# Ver tests
pytest tests/unit/test_phone.py::TestValidatePhone -v
```

#### "Birth date validation failed: Date is in future"

```bash
# Causa: Fecha de nacimiento futura

# Inválido: 2025-12-31 (futura)
# Válido: 1990-01-01 (pasada)

# Límite inferior: 1920-01-01
# Límite superior: hoy
```

### Problemas de Seguridad

#### "SQL Injection detected in audit"

```bash
# Causa: Código contiene f-string en SQL execute

# Búsqueda:
grep -r "execute.*f\"" app/

# NO HACER:
cur.execute(f"SELECT * FROM personas WHERE rut = '{rut}'")

# HACER:
cur.execute("SELECT * FROM personas WHERE rut = %s", (rut,))
```

#### "XSS vulnerability detected"

```bash
# Causa: Entrada de usuario no escapada

# Verificar con auditoría
python scripts/security_audit.py

# Asegurar que Pydantic valida:
# app/models/solicitud.py tiene validators
```

#### "Secrets found in code"

```bash
# Causa: Credenciales hardcodeadas

# Búsqueda:
python scripts/security_audit.py

# Si encuentra secrets:
# NO HACER:
DATABASE_PASSWORD = "produccion_secret_123"

# HACER:
# Guardar en .env (que está en .gitignore)
# O AWS Secrets Manager en producción
```

### Problemas de Encoding

#### "UnicodeDecodeError" con caracteres especiales

```bash
# Causa: Encoding incorrecto (especialmente con acentos)

# Solución: Asegurar UTF-8

# En Windows PowerShell:
$env:PYTHONIOENCODING = "utf-8"

# En archivos Python (primera línea):
# -*- coding: utf-8 -*-

# Verificar:
python -c "import sys; print(sys.getdefaultencoding())"  # Debe ser utf-8
```

#### "SyntaxError: Non-UTF-8 code starting with..."

```bash
# Causa: Archivo no tiene encoding declarado

# Solución: Agregar a primera línea del archivo
# -*- coding: utf-8 -*-
```

### Problemas de Performance

#### "Streamlit responde lentamente"

```bash
# Causa: Queries a BD son lentas

# Solución 1: Verificar índices
psql tpi_local -c "\d tpi.personas"

# Crear índices si faltan:
psql tpi_local -c "CREATE INDEX idx_leads_rut ON tpi.leads(rut)"

# Solución 2: Ver tiempo de queries
# Habilitar timing en psql:
# psql> \timing

# Solución 3: Optimizar queries
# Ver EXPLAIN plan
# psql> EXPLAIN SELECT * FROM tpi.leads WHERE rut = '12345678-5';
```

#### "Memoria agotada en pytest"

```bash
# Causa: Parallelismo consume demasiada RAM

# Solución: Ejecutar sin paralelismo
pytest -n 1 --tb=short

# O limitar workers
pytest -n 2
```

### Problemas Diversos

#### "ImportError: cannot import name 'get_db_connection'"

```bash
# Causa: Ruta de import incorrecta

# Verificar imports:
# ✓ from app.database.connection import get_db_connection
# ✗ from database.connection import get_db_connection
```

#### ".env file not found"

```bash
# Causa: Archivo .env no existe

# Solución: Crear desde .env.example
cp .env.example .env

# Editar valores:
nano .env  # Linux/Mac
notepad .env  # Windows
```

#### "Permission denied: .env"

```bash
# Causa: Permisos de archivo incorrectos

# Solución:
# Linux/Mac:
chmod 600 .env

# Windows (GUI):
# Click derecho > Properties > Security > Edit Permissions
```

#### "Version of Python not supported"

```bash
# Causa: Python < 3.12

# Verificar:
python --version  # Debe ser >= 3.12

# Cambiar a Python 3.12:
# Si tienes múltiples versiones:
python3.12 -m venv .venv

# Reactivar venv y reinstalar
.venv/Scripts/Activate.ps1
pip install -e ".[dev]"
```

---

## ⚡ Comandos Útiles

### Desarrollo

```bash
# Ver cambios en tiempo real
pytest --tb=short -v --ff  # --ff = últimas fallos primero

# Ejecutar test específico
pytest tests/unit/test_rut.py::TestValidateRut::test_valid_ruts -v

# Con output
pytest -s  # Muestra print() statements

# Paralelo (rápido)
pip install pytest-xdist
pytest -n auto  # Usa todos los cores
```

### Base de Datos

```bash
# Conectarse a BD
psql -h localhost -U tpi_app -d tpi_local

# Comandos en psql
\dt          # Listar tablas
\d tpi.personas  # Describir tabla
SELECT COUNT(*) FROM tpi.personas;  # Contar
\q          # Salir
```

### Linting y Formato

```bash
# Ver problemas de código
ruff check .

# Arreglar automáticamente
ruff format .

# Type checking
mypy app/

# Todos
ruff check . && ruff format . && mypy app/
```

### Logs

```bash
# Ver últimas líneas
tail -f logs/backoffice.log

# Búsqueda de errores
grep ERROR logs/backoffice.log

# Últimos 50 errores
grep ERROR logs/backoffice.log | tail -50
```

### Limpieza

```bash
# Limpiar cache de Python
find . -type d -name __pycache__ -exec rm -r {} +

# Limpiar cache de Streamlit
rm -rf ~/.streamlit/cache

# Limpiar archivos de test
rm -rf .pytest_cache/
rm -rf htmlcov/
```

---

## ✅ Validación Completa

### Checklist Completo (10 min)

```bash
# 1. Dependencias
pip check

# 2. BD
python scripts/verify_database_connection.py

# 3. Estructura
python scripts/verify_project_structure.py

# 4. Tests unitarios (30s)
pytest tests/unit/ -q

# 5. Tests integración (1m)
pytest tests/integration/ -q

# 6. Tests E2E (1-2m)
pytest tests/e2e/ -q

# 7. Tests seguridad
pytest tests/security/ -q

# 8. Linting
ruff check .

# 9. Streamlit (manual)
streamlit run app/streamlit_app.py
# Visitar http://localhost:8501
# Probar registro y consultas
```

Si todo muestra ✅, ¡la aplicación está lista para usar!

---

## 📚 Documentación Adicional

- [README.md](README.md) - Visión general
- [docs/SEGURIDAD.md](docs/SEGURIDAD.md) - Seguridad
- [docs/DECISIONES_TECNICAS.md](docs/DECISIONES_TECNICAS.md) - Arquitectura
- [docs/ETAPA4_RESUMEN.md](docs/ETAPA4_RESUMEN.md) - UI Streamlit
- [tests/README.md](tests/README.md) - Testing

---

**Last Updated:** 2024  
**Version:** 1.0.0 MVP - Etapa 5 Completa
