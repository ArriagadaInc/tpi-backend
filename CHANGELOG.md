# Changelog

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/) y este proyecto adhiere a [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### ✅ Agregado

- **Simulador de renta vitalicia en el CRM (perfil ejecutivo)** (SIM-RV-V1)
  - Motor puro `app/simulador_pension` que reproduce el simulador de referencia dentro de ±1 UF (435/435 casos del fixture).
  - Panel y formulario en el detalle del lead, visible solo para `executive` y superusuarios `ceo`/`cto` (403 real para el resto).
  - PDF efímero en memoria con escape de marcado, sin persistencia de entradas ni resultados.
  - Evento funcional append-only en `tpi.auditoria` sin PII (`app/services/simulador_auditoria.py`).
  - Dependencia nueva: `reportlab==5.0.1`.

### 🔄 Cambiado

- **Ajustes de uso del CRM y del simulador** (SIM-UX-AJUSTES)
  - Los errores de validación del formulario del simulador (p. ej. edad fuera de rango) se muestran en la misma pantalla, en un aviso arriba del formulario, conservando lo ingresado, con HTTP 422 y mensaje claro en español; ya no se responde con una pantalla de texto aparte.
  - En el detalle del lead se elimina el botón antiguo «Abrir simulación» y queda solo «Abrir simulador» del panel nuevo (visible para `executive`, `ceo` y `cto`).
  - Cabecera del CRM: «Volver al sitio» pasa a «Home» y «Salir» pasa a «Cerrar sesión».
  - El CRM deja de llamarse «CRM Lite»: ahora se muestra «CRM» en títulos de página, cabecera, insignia, kickers, login y la app Streamlit.

---

## [0.2.0] - 2026-10-12

### ✅ Agregado

- **Logo oficial de CRM Lite** (#64)
  - Reemplaza el logo temporal por el logo oficial de Tu Pensión Inteligente.
  - Se renderiza en la cabecera y en la pantalla de acceso de CRM Lite.
  - Servido como recurso estático local (`app/web/static/img/official-logo-on-light.png` y `app/web/static/img/official-logo-on-dark.png`), sin cargas desde orígenes externos.
  - Variante para tema oscuro (`official-logo-on-dark.png`) seleccionada vía CSS.
  - Texto alternativo accesible en ambas instancias.

### 🔒 Seguridad

- **Mitigación de CVE-2026-85091 (zlib)** (#65)
  - Se fija `zlib=1.3.2-r1` en la imagen de la aplicación (`Dockerfile`).
  - Se actualiza `zlib` en la imagen de Caddy (`deployment/caddy/Dockerfile`).
  - Se actualizan los contratos de supply chain y el test de imagen de la aplicación.

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

**Versión Actual:** 0.2.0  
**Próxima Versión:** 0.3.0 (por definir)

---

## Histórico de Versiones

| Versión | Fecha | Estado | Hito |
|---------|-------|--------|------|
| 0.2.0 | 12 Oct 2026 | 🚀 RELEASE DEV | Logo oficial de CRM Lite + mitigación zlib |
| 0.1.0 | 31 Jul 2026 | ✅ VALIDADO | MVP1 Completado |
| 0.0.1 | 30 Jul 2026 | ✅ INICIAL | Estructura Base |

---

**Última actualización:** 12 Octubre 2026  
**Responsable:** Equipo TPI Back-office  
**Contacto:** dev@tupensioninteligente.cl
