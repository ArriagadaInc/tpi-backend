# Changelog

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/) y este proyecto adhiere a [Semantic Versioning](https://semver.org/).

---

## [0.1.0] - 2026-07-31

### ✅ Agregado

- **Validación Completa MVP1**
  - Validación de conexión a PostgreSQL
  - Validación de catálogos (género, estado civil, AFP)
  - Flujo completo de registro (persona → lead → consentimientos)
  - Documentación de validación detallada

- **Documentación Actualizada**
  - README.md mejorado con estado de validación
  - Nuevo documento: [docs/MVP1_VALIDACION.md](docs/MVP1_VALIDACION.md)
  - Nuevo documento: [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md)
  - Nuevo documento: CHANGELOG.md (este archivo)

- **Herramientas de Validación**
  - Script: `test_connection.py` - Validar conexión a BD
  - Script: `test_solicitud_flow.py` - Validar flujo de registro
  - Script: `explore_schema.py` - Explorar estructura de tablas
  - Script: `generar_informe.py` - Generar reporte de validación
  - Script: `check_postgres.py` - Verificar usuarios de BD
  - Script: `check_streamlit.py` - Verificar importación de Streamlit
  - Script: `list_tables.py` - Listar tablas del esquema

- **GitHub Actions CI/CD**
  - Workflow `.github/workflows/ci.yml` para:
    - Linting (ruff, black)
    - Type checking (mypy)
    - Pruebas unitarias
    - Cobertura de código
    - Auditoría de seguridad

### 🔧 Corregido

- **Problema 1:** Credenciales incorrectas en `.env`
  - Usuario `tpi_app` no existe
  - Solución: Usar usuario `postgres` con contraseña correcta

- **Problema 2:** Módulo `psycopg.pool` no disponible
  - psycopg v3 separó pool en paquete independiente
  - Solución: Instalar `psycopg-pool` y actualizar imports

- **Problema 3:** URL de conexión con prefijo SQLAlchemy
  - `ConnectionPool` requiere formato `postgresql://` no `postgresql+psycopg://`
  - Solución: Actualizar `get_database_url()` en `app/config/settings.py`

- **Problema 4:** Parámetro `row_factory` inválido en constructor
  - `psycopg_pool.ConnectionPool` no acepta `row_factory` en constructor
  - Solución: Aplicar `row_factory` en `get_connection()` después de obtener conexión

- **Problema 5:** Columnas faltantes en INSERT de `leads`
  - Query no incluía columnas requeridas: `fecha_ingreso`, `origen_lead`, `fuente_actual`
  - Solución: Agregar columnas y parámetros correspondientes

- **Problema 6:** Columna `id_persona` faltante en INSERT de `consentimientos`
  - Tabla requiere `id_persona` pero no se insertaba
  - Solución: Incluir `id_persona` en parámetros de INSERT

### 📋 Cambios

- Actualizar archivo `.env` con credenciales correctas
- Actualizar `app/config/settings.py` para URL de conexión correcta
- Actualizar `app/database/connection.py` para psycopg_pool compatible
- Actualizar `app/repositories/solicitud_repository.py` con INSERT correcto
- README.md completamente reescrito con información de validación
- Agregar documentación de seguridad en SECURITY.md

### 📚 Documentación

- [x] Documento de validación MVP1 completo
- [x] Estado del proyecto documentado
- [x] Roadmap detallado
- [x] Métricas y cobertura
- [x] Pasos siguiente claros

---

## [0.0.1] - 2026-07-30 (Initial Release - Anterior a esta validación)

### ✅ Agregado

- Estructura base Streamlit con 3 páginas
- Conexión a PostgreSQL con pool
- Modelo de datos completo
- Validadores (RUT, email, teléfono)
- Catálogos dinámicos
- Suite de pruebas unitarias
- GitHub Actions workflow
- Documentación arquitectura
- Docker y docker-compose
- License MIT
- Contributing guide
- Security policy

### 📋 Conocidos

- Sin autenticación (es MVP)
- Sin rate limiting (es MVP)
- Validadores secundarios necesitan revisión

---

## Cómo Contribuir

Para contribuir cambios a este changelog:

1. Crea una rama: `git checkout -b feature/description`
2. Haz tus cambios
3. Actualiza este CHANGELOG.md con:
   - Sección `[Unreleased]` si aún no existe
   - Categorías: Added, Changed, Deprecated, Removed, Fixed, Security
4. Commit con mensaje descriptivo
5. Push y abre Pull Request

---

## Versionado

Este proyecto sigue [Semantic Versioning](https://semver.org/):

- MAJOR: Cambios incompatibles
- MINOR: Funcionalidades nuevas compatibles
- PATCH: Correcciones de bugs

**Versión Actual:** 0.1.0  
**Próxima Versión:** 0.2.0 (Autenticación MVP2)

---

## Histórico de Versiones

| Versión | Fecha | Estado | Hito |
|---------|-------|--------|------|
| 0.1.0 | 31 Jul 2026 | ✅ VALIDADO | MVP1 Completado |
| 0.0.1 | 30 Jul 2026 | ✅ INICIAL | Estructura Base |

---

**Última actualización:** 31 Julio 2026  
**Responsable:** Equipo TPI Back-office  
**Contacto:** dev@tupensioninteligente.cl
