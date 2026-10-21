# Developer — CONTEXT (vista curada)

Carga esta vista; abre las fuentes solo en la seccion indicada cuando la tarea lo requiera.

## Producto

TPI capta leads de simulacion de pension (sitio publico) y los gestiona en un backoffice privado
(CRM Lite). Solo AWS DEV con datos sinteticos.

## Arquitectura vigente

```text
front/ (estatico, Caddy) + app/api (FastAPI, POST /api/v1/leads, GET /api/v1/catalogs)
app/web (FastAPI + Jinja2, backoffice CRM Lite, uvicorn app.web.main:app :8501)
  -> app/services/solicitud_service.py -> app/repositories/solicitud_repository.py
  -> PostgreSQL (psycopg3 + psycopg_pool, esquema tpi, sin ORM)
  -> app/notifications (LeadCreatedEvent post-commit, SNS)
Auth: app/auth SimpleDevAuth (Argon2id, DEV-only), roles tester/admin/advisor/executive/operations/readonly/ceo/cto
Streamlit fue retirado (SEG-DESACOPLAR-STREAMLIT): no existe codigo ni dependencia de Streamlit; no lo reintroduzcas
```

## Reglas de dominio y seguridad

- PII completa solo para `ceo`/`cto`; los demas reciben masking **server-side** y el HTML servido no
  contiene PII completa (`app/security/masking.py`, `SolicitudService.can_view_full_pii`).
- `tpi.asignaciones` es la fuente operacional de la relacion lead-asesor; `leads.raw_payload` no.
- `estado_lead='asignado'` solo por la operacion de asignacion; una sola asignacion `activa` por lead.
- `tpi.auditoria` append-only para `tpi_app`; `asignado_por` = `AuthenticatedUser.subject`.
- CSRF en operaciones mutables; cookies HttpOnly/Secure/SameSite=lax; guards fail-closed.
- No inventar modelo de datos: `docs/database/02_PHYSICAL_SCHEMA.md` y `03_BUSINESS_RULES.md`.
- Migraciones: scripts versionados en `scripts/sql/` con preflight y rollback; bootstrap de tests en
  `scripts/init_test_database.py`. Nunca reejecutar 005/006. Ejecucion en AWS = clase D, fuera del Harness.
- Secretos solo por entorno/Secrets Manager; nunca en codigo, tests, logs ni docs.

## Limites del guard (bloqueos de forma)

El guard (`harness/policies.yaml`) revisa el **texto** de cada comando de shell, no solo lo que hace. Estos
bloqueos son de forma, detienen la sesion y son definitivos: no busques rodeos; detente y reporta.

- Un comando que contenga en cualquier parte (heredoc, `echo`, `grep`, argumento, comentario) un texto de
  `forbidden_everywhere` se deniega completo, aunque solo lo nombre: el SDK de AWS para Python (`boto3`; AWS va
  por `python scripts/harness/aws_guard.py`), nombres de secretos (`DATABASE_PASSWORD`, `AUTH_USERS_JSON`,
  `WEB_SESSION_SECRET`...), `docker push`/`docker login`, `git push` forzado o a `main`, `git reset --hard`,
  `git clean`, `git checkout --` y el script de decisiones humanas. No pongas esos textos en un comando; si
  necesitas listar o buscar paquetes, hazlo con las herramientas de lectura o con un `python -c` de una linea
  que no los nombre.
- No crees archivos sueltos en la raiz del worktree (scripts de analisis, notas, salidas temporales): solo se
  escribe dentro del alcance de la tarea (`app/**`, `tests/**`, `scripts/*.py`, `docs/**`...). Para un analisis
  puntual usa un `python -c` de una linea, por ejemplo leyendo un JSON por la entrada estandar.
- `agents/**`, `harness/**`, `tasks/**`, `evidence/**` y `progress/decisions.md` no son escribibles por el
  Developer; `.github/**`, `Dockerfile`, `deployment/**` y `docker-compose*.yml` solo en tareas de clase C, y
  `requirements/**` y `pyproject.toml` solo con `allow_lockfile_update: true`.

## Calidad

- Gates: `harness/project-profile.yaml` `quality_gates` (CI: `.github/workflows/ci.yml`).
- Tests validan comportamiento y riesgo, no solo cobertura (`docs/ENGINEERING_STANDARDS.md`).
- Markers pytest: unit, integration (PostgreSQL), e2e, security.
- Lockfiles solo con `allow_lockfile_update: true` en la tarea.

## Fuentes

| Necesidad | Fuente (autoridad) |
| --- | --- |
| Modelo y reglas de datos | `docs/database/` (canonical) |
| Decisiones H2.4/H2.5 | `docs/DECISIONES_TECNICAS.md` (canonical; decision 4 superada) |
| Estados CRM y roles | `docs/H3_3_CRM_LITE_WEB_UX.md` secciones 4 y 6 (historical para version/cierre) |
| Deuda H3.3.1 | `docs/BITACORA.md` entrada 2026-09-12; issue #50 |
| Clasificacion de cambios A-E | `docs/cicd/TPI_Contrato_CICD_AWS_v2.md` seccion 2 |
| DoD | `docs/ENGINEERING_STANDARDS.md` (cobertura rige 85%) |

## No es estado actual

Version labels, SHAs y hostnames historicos de docs H2/H3 y `docs/PROJECT_STATUS.md`.
