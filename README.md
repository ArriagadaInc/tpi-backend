# Tu Pensión Inteligente - Back-office MVP

**Prototipo funcional de captura y consulta de solicitudes de simulación**

> **Estado:** ✅ MVP1 Validado y listo para demostración local (actualizado 1 Agosto 2026)

Este es un MVP (Producto Mínimo Viable) en Streamlit que demuestra la capacidad de:
- ✅ Registrar solicitudes de simulación desde un formulario web
- ✅ Validar y normalizar datos (RUT, email, teléfono)
- ✅ Almacenar en PostgreSQL con relaciones intactas
- ✅ Consultar registros existentes
- ✅ Visualizar trazabilidad básica
- ✅ Cargar selectores dinámicos desde catálogos

## ⚠️ Importante

- **Ambiente**: Desarrollo local y aws-dev por configuración
- **Datos**: Usar solo datos ficticios
- **Seguridad**: MVP sin autenticación (se implementará en producción)
- **Base de datos**: Conecta al esquema TPI del repositorio `tpi-data-pipeline`
- **Catálogos**: Solo lectura - se carga desde `catalogo_genero`, `catalogo_estado_civil`, `catalogo_afp`

---

## 📊 Estado de Validación MVP1

| Validación | Estado | Detalles |
|-----------|--------|----------|
| Conexión PostgreSQL | ✅ EXITOSA | PostgreSQL 17.6, BD tpi_local |
| Catálogos (Género, Estado Civil, AFP) | ✅ EXITOSA | Todos disponibles y cargados |
| Flujo de Registro Completo | ✅ EXITOSO | Persona → Lead → Consentimientos |
| Suite de Pruebas | ✅ EXITOSA | 153/153 pruebas aprobadas, 0 fallos, 0 omitidos |
| Aplicación Streamlit | ✅ FUNCIONAL | 3 páginas operativas y flujo de registro/listado/persistencia verificado |

**Última validación:** 1 Agosto 2026  
**Documentación de validación:** Ver [docs/INFORME_CORRECCION_MVP1.md](docs/INFORME_CORRECCION_MVP1.md)

---

## Requisitos

- Python 3.12+ (probado con 3.14)
- PostgreSQL 12+ (probado con 17.6)
- pip o poetry para instalar dependencias

## Instalación Rápida

### 1. Clonar el repositorio

```bash
git clone https://github.com/ArriagadaInc/tpi-backend.git
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

### 4. Configurar variables de entorno

```bash
# Copiar archivo de ejemplo
cp .env.example .env

# Editar .env con tus credenciales de PostgreSQL locales
# Ver archivo .env.example para referencia
```

**Valores para desarrollo local (con tpi-data-pipeline ejecutándose):**
```env
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=tpi_local
DATABASE_USER=postgres
DATABASE_PASSWORD=<tu_contraseña_postgres>
DATABASE_SCHEMA=tpi
APP_ENV=local
DATABASE_SSLMODE=disable
```

⚠️ **IMPORTANTE:** No commits las credenciales en Git. Usar git update-index --assume-unchanged .env`r

Para configurar ws-dev o producción, ver [docs/AWS_RDS_CONNECTION.md](docs/AWS_RDS_CONNECTION.md).

### 5. Ejecutar la aplicación

```bash
streamlit run app/streamlit_app.py
```

La aplicación se abrirá en `http://localhost:8501`

---

## 🚀 Ejecutar en Docker

```bash
# Construir imagen
docker build -t tpi-backoffice .

# Validar la topologia declarada de despliegue
docker compose config --quiet
docker compose build streamlit
```

El Compose versionado prepara Caddy como unico punto de entrada y Streamlit en
la red interna del contenedor. Para la configuracion local, base de datos,
quality gates y autenticacion DEV, ver
[docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md).

---

## 📝 Uso

### Registrar una Solicitud

1. Ir a página **Registrar Solicitud**
2. Completar formulario:
   - RUT (formato: 12.345.678-5 o 12345678-5)
   - Nombre completo
   - Email
   - Teléfono
   - Fecha de nacimiento
   - Género, Estado Civil, AFP (desplegables)
   - Saldo AFP (opcional)
   - Aceptar términos y políticas
3. Enviar
4. Confirmación aparecerá si la inserción fue exitosa

### Consultar Solicitudes

Ir a página **Solicitudes Registradas** para ver listado con paginación

### Trazabilidad

Ir a página **Trazabilidad** para ver métricas y trazabilidad básica de solicitudes

---

## 🧪 Testing

### Ejecutar pruebas unitarias

```bash
pytest tests/unit/ -v
```

### Ejecutar pruebas de integración

```bash
pytest tests/integration/ -v
```

### Ver cobertura

```bash
pytest tests/ --cov=app --cov-report=html
```

---

## 📂 Estructura del Proyecto

```
tu-pension-inteligente-backoffice/
├── app/
│   ├── streamlit_app.py           # Entrada principal
│   ├── pages/                     # Páginas Streamlit
│   │   ├── 1_registrar_solicitud.py
│   │   ├── 2_solicitudes_registradas.py
│   │   └── 3_trazabilidad.py
│   ├── components/                # Componentes reutilizables
│   ├── config/                    # Configuración (settings)
│   ├── database/                  # Conexión y pool
│   ├── models/                    # Modelos Pydantic
│   ├── repositories/              # Acceso a datos
│   ├── services/                  # Lógica de negocio
│   ├── validators/                # Validadores (RUT, email, etc)
│   └── security/                  # Enmascaramiento de datos
├── tests/
│   ├── unit/                      # Pruebas unitarias
│   ├── integration/               # Pruebas de integración
│   ├── e2e/                       # Pruebas end-to-end
│   └── security/                  # Pruebas de seguridad
├── docs/                          # Documentación
├── scripts/                       # Scripts de utilidad
├── pyproject.toml                 # Dependencias
├── Dockerfile                     # Containerización
├── docker-compose.yml             # Orquestación
└── README.md                      # Este archivo
```

---

## 🔗 Dependencias Principales

- **streamlit** - Framework web interactivo
- **psycopg** - Driver PostgreSQL
- **sqlalchemy** - ORM
- **pydantic** - Validación de datos
- **python-dotenv** - Manejo de variables de entorno

---

## 📚 Documentación Adicional

- [Preparación H2.1](docs/H2_1_PREPARACION_DESPLIEGUE.md) - Base técnica para despliegue reproducible en AWS DEV
- [Despliegue H2.2 AWS DEV](docs/H2_2_AWS_DEV_DEPLOYMENT.md) - Elastic Beanstalk, Docker, RDS, rollback y operación DEV
- [H2.3 limpieza DEV de leads ficticios](docs/H2_3_DEV_TEST_LEAD_CLEANUP.md) - Guard de ambiente, permisos minimos y rollback
- [Validación MVP1](docs/MVP1_VALIDACION.md) - Reporte completo de validación
- [Conexión PostgreSQL y AWS RDS](docs/AWS_RDS_CONNECTION.md) - Configuración por ambiente, SSL, permisos, pruebas y rollback
- [Arquitectura](docs/ARCHITECTURE.md) - Diseño del sistema
- [Decisiones Técnicas](docs/DECISIONES_TECNICAS.md) - Justificación de choices
- [Deployment](docs/DEPLOYMENT.md) - Guía de despliegue
- [Seguridad](SECURITY.md) - Política de seguridad
- [Contribución](CONTRIBUTING.md) - Cómo contribuir

---

## 🐛 Problemas Conocidos

### MVP1 (Conocidos y Resueltos)
- ✅ Credenciales de BD (resuelto: actualizado a user postgres)
- ✅ psycopg_pool no disponible (resuelto: instalado paquete)
- ✅ URL de conexión con prefijo SQLAlchemy (resuelto: formato correcto postgresql://)
- ✅ Columnas faltantes en INSERT (resuelto: agregadas fecha_ingreso, origen_lead, etc)

### Limitaciones Actuales
- ⚠️ Sin autenticación (MVP - se implementará en producción)
- ⚠️ Sin rate limiting (MVP - se implementará en producción)
- ⚠️ Sin cifrado de datos en tránsito (MVP - HTTPS en producción)

---

## 🤝 Contribución

Por favor consulta [CONTRIBUTING.md](CONTRIBUTING.md) para:
- Proceso de contribución
- Estándares de código
- Cómo reportar bugs
- Cómo sugerir features

## 📄 Licencia

MIT - Ver [LICENSE](LICENSE)

---

## 📞 Contacto

- **Equipo:** Tu Pensión Inteligente
- **Email:** dev@tupensioninteligente.cl
- **GitHub:** [ArriagadaInc/tpi-backend](https://github.com/ArriagadaInc/tpi-backend)
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
4. **Sin auditoría operativa expuesta en la UI** - El MVP muestra metadatos básicos (`created_at`, `estado_lead`) aunque el esquema contiene tablas operativas adicionales no consumidas por esta app
5. **Conexión AWS dev soportada por configuración** - La app puede conectarse a Amazon RDS mediante variables de entorno y SSL; el despliegue productivo sigue pendiente
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
1. [ ] Promover la configuración validada de `aws-dev` a un despliegue administrado
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
