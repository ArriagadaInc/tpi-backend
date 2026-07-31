# Tu Pensión Inteligente - Back-office MVP

**Prototipo funcional de captura y consulta de solicitudes de simulación**

Este es un MVP (Producto Mínimo Viable) en Streamlit que demuestra la capacidad de:
- Registrar solicitudes de simulación desde un formulario web
- Validar y normalizar datos
- Almacenar en PostgreSQL
- Consultar registros existentes
- Visualizar trazabilidad básica

## ⚠️ Importante

- **Ambiente**: Demostrativo local únicamente
- **Datos**: Usar solo datos ficticios
- **Seguridad**: MVP sin autenticación (se implementará en producción)
- **Base de datos**: Conecta al esquema TPI del repositorio `tpi-data-pipeline`

---

## Requisitos

- Python 3.12+
- PostgreSQL 12+ (ejecutando el proyecto `tpi-data-pipeline`)
- pip o poetry para instalar dependencias

## Instalación

### 1. Clonar el repositorio

```bash
cd c:\desarrollos
git clone <repositorio-url> tu-pension-inteligente-backoffice
cd tu-pension-inteligente-backoffice
```

### 2. Crear entorno virtual

**En Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**En Linux/Mac:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -e ".[dev]"
```

O con poetry:
```bash
poetry install
poetry shell
```

### 4. Configurar variables de entorno

```bash
# Copiar archivo de ejemplo
cp .env.example .env

# Editar .env con tus credenciales de PostgreSQL
# (usar las mismas del proyecto tpi-data-pipeline)
```

Valores típicos para desarrollo local:
```
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=tpi_local
DATABASE_USER=tpi_app
DATABASE_PASSWORD=tu_contraseña
DATABASE_SCHEMA=tpi
```

### 5. Verificar conexión a PostgreSQL

```bash
python scripts/verify_database_connection.py
```

Deberías ver:
```
✅ TODAS LAS VERIFICACIONES PASARON CORRECTAMENTE
```

## Uso

### Ejecutar la aplicación Streamlit

```bash
streamlit run app/streamlit_app.py
```

La aplicación se abrirá en `http://localhost:8501`

### Ejecutar pruebas

```bash
pytest
```

Con cobertura:
```bash
pytest --cov=app --cov-report=html
```

### Verificar código (linting)

```bash
ruff check .
ruff format . --check
```

---

## Arquitectura

```
Interfaz Streamlit (app/streamlit_app.py)
        ↓
Páginas y Componentes (app/pages/, app/components/)
        ↓
Servicios de Negocio (app/services/)
        ↓
Repositorio de Datos (app/repositories/)
        ↓
Base de Datos PostgreSQL (esquema tpi)
```

### Estructura del proyecto

```
tu-pension-inteligente-backoffice/
├── app/
│   ├── __init__.py
│   ├── streamlit_app.py          # Aplicación principal
│   ├── pages/                    # Páginas de Streamlit
│   │   ├── 1_registrar_solicitud.py
│   │   ├── 2_solicitudes_registradas.py
│   │   └── 3_trazabilidad.py
│   ├── components/               # Componentes reutilizables
│   ├── models/                   # Modelos Pydantic
│   │   └── solicitud.py
│   ├── services/                 # Lógica de negocio
│   │   └── solicitud_service.py
│   ├── repositories/             # Acceso a datos
│   │   └── solicitud_repository.py
│   ├── validators/               # Validadores
│   │   ├── rut.py
│   │   ├── phone.py
│   │   └── email.py
│   ├── database/                 # Conexión y health check
│   │   ├── connection.py
│   │   └── healthcheck.py
│   ├── security/                 # Enmascaramiento de datos
│   │   └── masking.py
│   └── config/                   # Configuración
│       └── settings.py
├── tests/
│   ├── unit/
│   └── integration/
├── scripts/
│   └── verify_database_connection.py
├── .env.example                  # Variables de entorno (ejemplo)
├── .gitignore
├── pyproject.toml                # Dependencias y configuración
└── README.md
```

## Tablas utilizadas

### De solo lectura (catalógos)
- `tpi.catalogo_afp` - AFP disponibles
- `tpi.catalogo_genero` - Géneros
- `tpi.catalogo_estado_civil` - Estados civiles

### Lectura/Escritura
- `tpi.personas` - Datos de la persona
- `tpi.leads` - Solicitud de simulación
- `tpi.consentimientos` - Aceptación de T&C y privacidad

## Validaciones implementadas

### Nombre completo
- Requerido
- 3-200 caracteres
- Sin números puros
- Espacios normalizados

### RUT chileno
- Requerido
- Módulo 11
- Acepta formatos: 12345678-5, 12.345.678-5, 12345678k
- Normaliza a: 12345678-5

### Email
- Requerido
- Estructura válida
- Máximo 254 caracteres
- Normaliza a minúsculas

### Teléfono
- Requerido
- Formatos chilenos
- Normaliza a: +56912345678

### Fecha de nacimiento
- Requerida
- No futura
- Rango: 1920-2015

### Saldo AFP
- Requerido
- ≥ 0
- En pesos chilenos
- Sin decimales

### Consentimientos
- Aceptación de T&C (obligatoria)
- Aceptación de privacidad (obligatoria)
- Autorización de contacto (obligatoria)

## Enmascaramiento de datos

En la tabla de solicitudes registradas, los datos sensibles aparecen enmascarados:

```
RUT:      12.***.***-5
Email:    us***@dominio.cl
Teléfono: +56 9 **** 5678
```

## Limitaciones del MVP

1. **Sin autenticación** - Acceso abierto (requiere autenticación en producción)
2. **Sin edición** - Solo registro y consulta
3. **Sin eliminación** - Registros permanentes
4. **Sin auditoría de eventos** - Solo metadatos (`created_at`, `estado_lead`)
5. **Sin integración AWS** - Local únicamente (preparado para migración)
6. **Sin envío de correos** - No se implementa notificación
7. **Solo lectura del detalle** - Vista demostrativa de datos

## Pasos futuros

### Antes de producción
1. [ ] Implementar autenticación (OAuth2, JWT)
2. [ ] Agregar autorización por rol
3. [ ] Validar con SSL/TLS
4. [ ] Pruebas de carga
5. [ ] Auditoría completa de eventos

### Integración con AWS
1. [ ] Reemplazar PostgreSQL local con Amazon RDS
2. [ ] Usar AWS Secrets Manager para credenciales
3. [ ] Desplegar con ECS o AppRunner
4. [ ] Configurar API Gateway
5. [ ] Implementar Lambda para procesamiento async

### Características nuevas
1. [ ] Edición de solicitudes
2. [ ] Carga de documentos
3. [ ] Envío de correos de confirmación
4. [ ] Integración con WhatsApp
5. [ ] Dashboard de métricas
6. [ ] API REST (FastAPI)

## Desarrollo local

### Crear entorno de prueba limpio

```bash
# Crear una BD de test (si lo deseas)
createdb tpi_test

# Ejecutar pruebas
pytest -m unit
pytest -m integration
```

### Desplegar cambios

1. Crear rama feature: `git checkout -b feature/nueva-funcionalidad`
2. Hacer cambios y tests
3. Ejecutar `ruff format .` y `ruff check .`
4. Crear PR y mergear a `main`

## Soporte y contacto

Para dudas sobre el MVP o el repositorio de ingesta:
- Consulta [tpi-data-pipeline](https://github.com/ArriagadaInc/tpi-data-pipeline)
- Documentación de BD: `docs/BASE_DE_DATOS_TPI.md` (en tpi-data-pipeline)

---

**Última actualización**: 2026-07-31  
**Versión MVP**: 0.1.0  
**Status**: En desarrollo
