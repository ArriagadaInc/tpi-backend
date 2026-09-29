# H3.3 - CRM Lite Web UX

## 1. Resumen Ejecutivo

H3.3 cerró la transición del backoffice desde Streamlit hacia una capa web moderna basada en FastAPI + Jinja2 + CSS/JS local. El objetivo fue entregar una interfaz operacional para CRM Lite, reutilizando los servicios, repositorios y PostgreSQL RDS existentes, sin cambios de esquema ni de infraestructura base.

El hito quedó registrado como `CLOSED WITH DEFERRED ACCEPTANCE ITEMS` (ver `docs/BITACORA.md` 2026-09-12), quedando la deuda de RBAC/PII y asignación manual delegada al issue #50 (H3.3.1), implementados técnicamente y pendientes de verificación humana en DEV.

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
- masking de PII server-side por rol (CEO/CTO ven PII completa; roles restringidos reciben masking sin PII en HTML);
- control por roles y asignación manual;
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
- masking de PII server-side por rol (`CEO`/`CTO` sin masking);
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
- masking de PII por rol;
- asignación manual para roles autorizados;
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
- PII server-side masking (`can_view_full_pii` para CEO/CTO únicamente);
- `operations` sin cleanup;
- CSRF obligatorio;
- cookies `HttpOnly`, `Secure`, `SameSite=lax`;
- `WEB_MASK_PII` sin efecto sobre el masking (el masking es por rol, incondicional);
- `DEV_DELETE_ENABLED=false`;
- secretos fuera de Git;
- `AUTH_USERS_JSON` inyectado vía Secrets Manager / EB environment secrets.

## 8. Deployment AWS DEV

- Environment: `tpi-backoffice-dev-green`
- URL: `https://backoffice.dev.tupensioninteligente.cl`
- VersionLabel: `h3-3-crm-web-43101be-domainlocked-r1`
- Git Candidate SHA: `43101be7835088f93267bee85b0f11c8bc879867`
- Bundle SHA256: `007b14d4b439ea59afd13106b71edafbf902e564085581e7577770261c97282f`

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
- Human UX Acceptance → `pendiente` (requiere smoke autenticado en DEV para H3.3.1 AC-1..AC-4)

## 11. Validación Manual

- navegación operativa;
- bandeja funcional con RBAC PII por rol;
- detalle funcional con control de asignación manual;
- filtros y paginación activos;
- simulador accesible por configuración;
- estilos cargados correctamente;
- control de acceso y masking activos.

## 12. Release y Trazabilidad

- VersionLabel: `h3-3-crm-web-43101be-domainlocked-r1`
- Candidate SHA: `43101be7835088f93267bee85b0f11c8bc879867`
- PR Squash Merge SHA: `89a1c58643fc228024243d474c47986ab272257f`
- Bundle SHA256: `007b14d4b439ea59afd13106b71edafbf902e564085581e7577770261c97282f`
- Environment: `tpi-backoffice-dev-green`
- URL: `https://backoffice.dev.tupensioninteligente.cl`

CI final:

- Lint & Format: PASS
- Tests: PASS
- Security Audit: PASS
- Docker Build: PASS

## 13. Rollback

- EB Version: será determinada por el Deployer durante el preflight (LKG observado).
- Rollback = volver a la versión LKG exacta (version-only), sin reconstrucción de código antiguo.

## 14. Riesgos y Deuda Pendiente

- auditoría formal de eventos;
- evolución del seguimiento a entidad propia si se requiere analytics o edición individual;
- consolidación documental futura de operación DEV.

## 15. Estado Final

```text
H3.3 — CRM Lite Web UX
STATUS: CLOSED WITH DEFERRED ACCEPTANCE ITEMS (H3.3.1 pendiente de verificación)
AWS DEV: DEPLOYED (h3-3-crm-web-43101be-domainlocked-r1)
```

## 16. H3.3.3 — Historial operativo y Volver al sitio

H3.3.3 corrige dos regresiones del CRM Lite detectadas en el smoke humano de H3.3.2
(`KI-CRMLITE-VOLVER-AL-SITIO` y `KI-CRMLITE-TRAZABILIDAD-ASIGNACION`).

### Línea de tiempo unificada

La sección "Seguimiento y Notas Internas" muestra una única línea de tiempo
cronológica (America/Santiago) que fusiona:

- **Evento automático e inmutable de asignación**: fecha/hora, actor (identidad
  histórica `actor_subject`), asesor, transición `estado_anterior → estado_nuevo` y
  badge "Automático"; sin controles de edición ni eliminación.
- **Nota humana**: comportamiento actual, visualmente distinguida.

Estado vacío coherente cuando no hay notas ni eventos. Las notas existentes, el
masking de PII y el RBAC permanecen intactos.

El read model de trazabilidad vive en la vista `tpi.v_asignacion_auditoria`
(migracion 007), no en estado paralelo; la aplicacion lee la vista (nunca
`tpi.auditoria`) y resuelve el nombre del asesor con un `JOIN` seguro a
`tpi.asesores`. La resolucion de `display_name` desde `actor_subject` quedaria fuera
de alcance (requiere exponer el directorio de usuarios del secreto de autenticacion,
que incluye `password_hash`), por lo que se conserva `actor_subject` como identidad
historica y fallback obligatorio.

### "Volver al sitio"

El enlace "Volver al sitio" reutiliza `get_public_site_url()` y se integra en la Web
UX FastAPI/Jinja2 real:

- Solo visible para usuario autenticado (nunca en login ni superficies publicas).
- `href` exacto a `https://dev.tupensioninteligente.cl/` en DEV.
- Fail-closed ante URL ausente o invalida (la allowlist de `get_public_site_url`
  valida esquema, host, puerto y rechaza query, fragment y credenciales).
- No transfiere sesion, cookies, tokens, credenciales, query params ni fragmentos.

### Estado de la migracion 007

La migracion `007` (vista sobre `tpi.auditoria`) **no se ha aplicado en AWS RDS DEV
al cierre de la etapa de desarrollo**. Es `change_class D` y requiere Human Gate
explicito (migration candidate con SHA-256 del forward/rollback) antes de tocar AWS
RDS DEV.


