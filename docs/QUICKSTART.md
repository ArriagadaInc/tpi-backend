# GUÍA RÁPIDA - ETAPA 3 ✅

Instrucciones paso a paso para instalar y verificar que todo funciona correctamente.

## 1. Clonar y Configurar

```bash
# Navegar al directorio
cd c:\desarrollos\tu-pension-inteligente-backoffice

# Crear entorno virtual
python -m venv .venv

# Activar (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Activar (Windows CMD)
.venv\Scripts\activate.bat

# Activar (Linux/Mac)
source .venv/bin/activate
```

## 2. Instalar Dependencias

```bash
# Instalar con modo desarrollo (incluye pytest, ruff, etc)
pip install -e ".[dev]"

# Verificar que se instaló correctamente
pip list | grep -i streamlit
pip list | grep -i psycopg
```

## 3. Configurar Variables de Entorno

```bash
# Copiar plantilla (ya existe .env local)
# Solo asegurar que .env tiene credenciales correctas

# Editar .env con tus datos de PostgreSQL
nano .env   # Linux/Mac
notepad .env  # Windows (desde PowerShell: start .env)

# Variables requeridas:
# DATABASE_HOST=localhost
# DATABASE_PORT=5432
# DATABASE_NAME=tpi_local
# DATABASE_USER=tpi_app
# DATABASE_PASSWORD=<tu_contraseña>
# DATABASE_SCHEMA=tpi
```

## 4. Verificar Conexión a BD

```bash
# Ejecutar script de verificación
python scripts/verify_database_connection.py

# Salida esperada:
# ✅ TODAS LAS VERIFICACIONES PASARON CORRECTAMENTE
# Personas en DB: ...
# Leads en DB: ...
# AFP: 7 activos
# Géneros: 2 activos
# Estados civiles: 4 activos
```

Si falla, revisar:
- PostgreSQL está ejecutándose
- Credenciales en `.env` son correctas
- Base de datos `tpi_local` existe
- Esquema `tpi` existe

## 5. Verificar Estructura del Proyecto

```bash
# Generar árbol y verificar integridad
python scripts/verify_project_structure.py

# Debería mostrar:
# ✅ ESTRUCTURA DEL PROYECTO VERIFICADA CORRECTAMENTE
# ÁRBOL DEL PROYECTO:
# ... (árbol visual)
# Estadísticas:
# Archivos Python: 27+
# Líneas de código: 3000+
```

## 6. Ejecutar Pruebas Unitarias

```bash
# Todas las unitarias
pytest tests/unit/

# Salida esperada:
# tests/unit/test_rut.py::TestNormalizeRut ... PASSED
# tests/unit/test_rut.py::TestValidateRut ... PASSED
# ...
# ==== 80+ passed in X.XXs ====
```

## 7. Ejecutar Pruebas de Integración

```bash
# Todas las de integración (requieren BD)
pytest tests/integration/

# Salida esperada:
# tests/integration/test_solicitud_flow.py::TestSolicitudFlow ... PASSED
# ...
# ==== 10+ passed in X.XXs ====
```

## 8. Ejecutar Todas las Pruebas

```bash
# Con cobertura
pytest --cov=app --cov-report=html

# Salida esperada:
# ==== 95+ passed in X.XXs ====
# Name                        Stmts   Miss  Cover
# app/validators/rut.py         50      2   96%
# app/validators/phone.py       45      1   97%
# app/validators/email.py       40      2   95%
# ... (más módulos)
# TOTAL                        500     30   94%
#
# HTML report generated in htmlcov/index.html
```

Para ver el reporte:
```bash
# Windows
start htmlcov/index.html

# Linux/Mac
open htmlcov/index.html
```

## 9. Revisar Código (Linting)

```bash
# Verificar formato
ruff check .

# Formatear automáticamente
ruff format .

# Verificar type hints (mypy)
mypy app/
```

## 10. Revisar Documentación

```bash
# Leer documentación de proyecto
cat README.md

# Leer decisiones técnicas
cat docs/DECISIONES_TECNICAS.md

# Leer resumen de Etapa 3
cat docs/ETAPA3_RESUMEN.md

# Leer guía de testing
cat tests/README.md
```

---

## Comandos Útiles

```bash
# Ver ayuda de pytest
pytest --help

# Ejecutar test específico
pytest tests/unit/test_rut.py::TestValidateRut::test_valid_ruts

# Ejecutar con salida verbosa
pytest -vv

# Mostrar solo pruebas que fallan
pytest -x

# Ejecutar hasta primer fallo y detener
pytest --tb=short

# Ver qué se importaría
pytest --collect-only tests/unit/

# Ejecutar en paralelo (más rápido)
pip install pytest-xdist
pytest -n auto

# Coverage detallado por línea
pytest --cov=app --cov-report=term-missing --cov-report=html
```

## Troubleshooting

### "No module named 'app'"
```bash
# Reinstalar en modo editable
pip install -e .
```

### "Connection refused" a PostgreSQL
```bash
# Verificar que PostgreSQL está corriendo
# Windows: buscar "Services" y iniciar PostgreSQL
# Linux: sudo systemctl start postgresql
# Mac: brew services start postgresql
```

### "Database does not exist"
```bash
# Crear base de datos (desde tpi-data-pipeline)
cd ../tpi-data-pipeline
python setup_db.py
```

### "Permission denied" en .env
```bash
# Cambiar permisos
chmod 600 .env  # Linux/Mac
# Windows: Click derecho > Properties > Security
```

### "ModuleNotFoundError: No module named 'psycopg'"
```bash
# Instalar psycopg3
pip install psycopg[binary]
```

---

## Flujo de Desarrollo

```
1. Editar código
   ↓
2. pytest (unitarias)
   ↓
3. ruff check .
   ↓
4. pytest tests/integration/
   ↓
5. pytest --cov=app (cobertura)
   ↓
6. Confirmar cambios a Git
```

---

## Próximos Pasos (Etapa 4)

Una vez que todo funciona correctamente en Etapa 3:

```bash
# Continuar con Etapa 4 (UI Streamlit)
# El repositorio y servicio están listos para ser consumidos por Streamlit
```

---

## ✅ Checklist

- [ ] PostgreSQL ejecutándose
- [ ] Python 3.12 instalado
- [ ] `.env` configurado con credenciales
- [ ] `python scripts/verify_database_connection.py` → PASÓ ✅
- [ ] `python scripts/verify_project_structure.py` → PASÓ ✅
- [ ] `pytest tests/unit/` → PASÓ ✅
- [ ] `pytest tests/integration/` → PASÓ ✅
- [ ] `pytest --cov=app` → Cobertura > 80% ✅
- [ ] `ruff check .` → Sin errores ✅
- [ ] Leí `/docs/DECISIONES_TECNICAS.md`
- [ ] Leí `/docs/ETAPA3_RESUMEN.md`

Si todo está ✅, ¡Etapa 3 está COMPLETA! 🎉

---

## Soporte

Si algo no funciona:

1. Verificar `/docs/DECISIONES_TECNICAS.md` - Sección "Troubleshooting"
2. Revisar los logs: `tail -f logs/backoffice.log`
3. Ejecutar verificaciones:
   ```bash
   python scripts/verify_database_connection.py
   python scripts/verify_project_structure.py
   ```
4. Consultar `/tests/README.md`

---

**Versión**: 0.1.0 (MVP)  
**Fecha**: 2026-07-31  
**Status**: ✅ Etapa 3 COMPLETA
