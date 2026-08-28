# H3.3 - CRM Lite Web UX

## 1. Resumen Ejecutivo

H3.3 cerró la transición del backoffice desde Streamlit hacia una capa web moderna basada en FastAPI + Jinja2 + CSS/JS local. El objetivo fue entregar una interfaz operacional para CRM Lite, reutilizando los servicios, repositorios y PostgreSQL RDS existentes, sin cambios de esquema ni de infraestructura base.

El hito fue validado manualmente en AWS DEV y quedó cerrado con `Human UX Acceptance: PASS`.

## 2. Objetivo

- Reemplazar el front Streamlit del backoffice por CRM Lite Web.
- Mantener la arquitectura de datos y persistencia existente.
- Preservar separación entre presentación, dominio y acceso a datos.
- Entregar una base estable para operación y evolución futura.

## 3. Alcance

### Incluido

- login y logout;
- bandeja de leads;
- búsqueda por nombre/RUT;
- filtros por AFP, estado y fechas;
- ordenamiento y paginación;
- detalle de lead independiente;
- cambio de estado;
- seguimiento y notas incrementales;
- acceso al simulador;
- masking de PII;
- control por roles;
- cleanup DEV restringido.

### Modelo de datos de referencia

La imagen `Estructura BD.jpg` corresponde al modelo de datos propuesto para el dominio.
No debe leerse como un DDL literal del ambiente actual.

Puntos a tener en cuenta al comparar con la BD real:

- `ASIGNACIONES` existe como entidad operacional formal y no debe tratarse como un JSON embebido en `leads`.
- `ASESORES` es la entidad formal de destino para la asignación; la UI puede llamarla "Ejecutivo", pero el código debe usar `asesor` e `id_asesor`.
- El esquema físico observado usa `id_asesor`, `fecha_asignacion`, `asignado_por`, `regla_asignacion`, `estado_asignacion` y `observacion` en `tpi.asignaciones`.
- `estado_asignacion = 'activa'` es el valor canónico del contrato actual; la app debe impedir variantes y la migración candidata debe reforzar la unicidad activa por `id_lead`.
- `asignado` no debe exponerse como transición genérica de estado: solo puede llegar desde la operación de asignación válida.
- `AUDITORIA` también existe como tabla separada y se usa como trazabilidad funcional.
- `LEADS.raw_payload` permanece solo como campo auxiliar de ingestión; no se usa para relaciones operacionales.

### Excluido

- cambios de esquema;
- migraciones;
- nuevas tablas;
- cambios AWS estructurales;
- rediseño de infraestructura;
- nuevas reglas de negocio;
- auditoría formal;
- funciones destructivas para roles operacionales.

## 4. Arquitectura Final

```text
Browser
  ↓
Caddy / HTTPS
  ↓
FastAPI + Jinja2
  ↓
SolicitudService
  ↓
SolicitudRepository
  ↓
PostgreSQL RDS
```

Componentes transversales:

- autenticación simple-dev;
- sesiones web;
- CSRF en operaciones mutables;
- roles `tester`, `admin`, `advisor`, `executive`, `operations`, `readonly`, `ceo`, `cto`;
- masking de PII mediante `WEB_MASK_PII`;
- integración con simulador por configuración central;
- runtime Uvicorn `app.web.main:app` en puerto `8501`.

## 5. Funcionalidades Entregadas

- login/logout;
- bandeja de leads;
- búsqueda por nombre y RUT;
- filtros por AFP, estado y fechas;
- ordenamiento;
- paginación;
- detalle de lead;
- cambio de estado;
- seguimiento/notas;
- acceso al simulador;
- masking de PII;
- restricciones por rol;
- cleanup DEV restringido y deshabilitado para `operations`.

## 6. Contrato de Estados CRM

Estados canónicos:

- `nuevo`
- `prospecto`
- `asignado`
- `contactado`
- `citado`
- `en_tramite`
- `expediente`
- `ficha_generada`
- `cerrado`
- `perdido`
- `no_califica`
- `duplicado`
- `dormido`

Compatibilidad legacy:

- `pendiente` → `nuevo`
- `Citado` → `citado`
- `En trámite` / `en_tramite` → `en_tramite`
- `Cerrado` → `cerrado`

Valores ambiguos no normalizados automáticamente:

- `simulada`
- `aprobada`
- `descartado`
- `rechazado`
- `en gestion`

## 7. Seguridad

- autenticación server-side;
- roles explícitos en backend;
- `operations` sin cleanup;
- CSRF obligatorio;
- cookies `HttpOnly`, `Secure`, `SameSite=lax`;
- `WEB_MASK_PII=true`;
- `DEV_DELETE_ENABLED=false`;
- secretos fuera de Git;
- `AUTH_USERS_JSON` inyectado vía Secrets Manager / EB environment secrets.

## 8. Deployment AWS DEV

- Environment: `tpi-backoffice-dev-green`
- URL: `https://backoffice.dev.tupensioninteligente.cl`
- VersionLabel: `h3-3-crm-web-1574d79-r1`
- Git SHA: `1574d79920342d3da2bac8296de9020b8162c68f`
- App digest: `sha256:1f5bca0350e3f3229516643b1f1f5dcf05f6f13e826c6a444aa8640302b73922`

Estado final:

```text
Status       Ready
Health       Green
HealthStatus Ok
```

## 9. Incidentes y Resolución

### Secreto `AUTH_USERS_JSON` corrupto

- Se detectó una versión corrupta del secreto en Secrets Manager.
- Se identificó una versión previa válida.
- Se reconstruyó el payload preservando usuarios existentes.
- Se incorporó `diego.operaciones` con rol `operations`.
- Se generó una nueva versión válida.
- Se ejecutó `RestartAppServer`.
- El login volvió a funcionar.

### Assets estáticos con esquema absoluto

- El HTML referenciaba CSS/JS con URLs absolutas detrás de Caddy/Uvicorn.
- Eso provocó mixed content y render sin estilos.
- La corrección fue usar rutas same-origin:
  - `/static/css/app.css`
  - `/static/js/app.js`

Lección:

- para assets same-origin detrás de reverse proxy, preferir rutas directas cuando el esquema absoluto no aporta valor.

## 10. Validación Técnica

- `GET /login` → `200`
- `POST /login` → exitoso
- `GET /leads` → `200`
- CSS → `200`
- JS → `200`
- mixed content → no
- visual CSS loaded → yes
- Human UX Acceptance → `PASS`

## 11. Validación Manual

- navegación operativa;
- bandeja funcional;
- detalle funcional;
- filtros y paginación activos;
- simulador accesible por configuración;
- estilos cargados correctamente;
- control de acceso y masking activos.

## 12. Release y Trazabilidad

- Git SHA: `1574d79920342d3da2bac8296de9020b8162c68f`
- App tag: `h3-3-1574d79`
- App digest: `sha256:1f5bca0350e3f3229516643b1f1f5dcf05f6f13e826c6a444aa8640302b73922`
- EB Version: `h3-3-crm-web-1574d79-r1`
- Environment: `tpi-backoffice-dev-green`
- URL: `https://backoffice.dev.tupensioninteligente.cl`

CI final:

- Lint & Format: PASS
- Tests: PASS
- Security Audit: PASS
- Docker Build: PASS

## 13. Rollback

- EB Version: `h3-3-crm-web-0ce8023-r1`
- App digest: `sha256:31380084bd13cb8545087d512297e957c777308ea999ddabff7df6db82408926`

Rollback = volver a esa versión exacta, sin reconstrucción de código antiguo.

## 14. Riesgos y Deuda Pendiente

- auditoría formal de eventos;
- evolución del seguimiento a entidad propia si se requiere analytics o edición individual;
- consolidación documental futura de operación DEV.

## 15. Estado Final

```text
H3.3 — CRM Lite Web UX
STATUS: CLOSED
AWS DEV: DEPLOYED
HUMAN UX ACCEPTANCE: PASS
```

