# H3.3.5 — Matriz de Cobertura de Requisitos (Requirements Coverage Gate)

Tarea: `H3.3.5 Asesores DEV y cartera propia`
Baseline: `origin/main@3051a6271e1626b40fe24a744abe097cab1ab0fe`
Rol: Developer (runtime deepseek). Estado al crear esta matriz: `DEVELOPING`.

> **Rework 1/3 (post `review-01.json`):** esta matriz se actualiza para citar pruebas que ejecutan
> el comportamiento real (PostgreSQL), no solo repositorios falsos. Hallazgos del Reviewer resueltos:
> F1 (orden de parámetros en `append_lead_comment`), F2 (pruebas PostgreSQL de cartera/ownership),
> F3/F7 (seed con `rol`/`estado_disponibilidad` explícitos, `lower(btrim(nombre))`, `IS DISTINCT FROM`,
> chequeo de base parametrizable), F4 (pruebas HTTP con repositorio real), F5/F8 (runbook con
> `RestartAppServer`/`UpdateEnvironment` y endpoint canónico), F6 (cobertura advisor restaurada por
> F2/F4), F9 (warning con `subject` + test de no-logging).

## Propósito

Trazabilidad completa requisito → AC → componente previsto → prueba automatizada → smoke/evidencia.
Todo requisito listado a continuación tiene, como mínimo, un AC, un componente de implementación
previsto y una prueba automatizada o un smoke/evidencia reproducible. Si alguno quedara sin
cobertura, el gate se considera `FAIL` y el desarrollo se detiene (BLOCKER).

## Leyenda

- `T` = prueba automatizada (unit / integration / e2e / security).
- `H` = verificación humana (smoke autenticado en DEV, ejecutada por el operador/Deployer en fases posteriores).
- `D` = artefacto documental/estático verificable sin ejecutar (seed SQL, runbook, evidencia).

## Matriz

| # | Requisito | AC | Componente previsto | Prueba automatizada | Smoke / Evidencia |
| --- | --- | --- | --- | --- | --- |
| 1 | Parseo compatible de `AUTH_USERS_JSON` (roles no-advisor) | AC-21 | `app/auth/simple_dev.py::_parse_user` (retrocompat: `advisor_id` opcional/ignorado) | `tests/unit/test_simple_dev_auth.py` + `tests/unit/test_h3_3_5_advisor_auth.py` | — |
| 2 | `advisor_id` en el modelo de usuario | AC-3, AC-4, AC-21 | `app/auth/models.py::AuthenticatedUser.advisor_id` (`UUID | None`) | `tests/unit/test_h3_3_5_advisor_auth.py` | — |
| 3 | Advisor sin vínculo (`advisor_id` ausente) | AC-21, D4 | `app/auth/simple_dev.py` + `app/services/solicitud_service.py::resolve_advisor_identity` | `tests/unit/test_h3_3_5_advisor_service.py` | AC-17 (smoke humano) |
| 4 | `advisor_id` malformado | AC-21 | `app/auth/simple_dev.py::_parse_advisor_id` (fail-closed a `None`) | `tests/unit/test_h3_3_5_advisor_auth.py` | — |
| 5 | `advisor_id` inexistente en `tpi.asesores` | AC-21 | `app/repositories/solicitud_repository.py::get_active_advisor_by_id` | `tests/unit/test_h3_3_5_advisor_service.py` | AC-17 |
| 6 | Advisor no activo (`estado_disponibilidad != activo`) | AC-21 | `get_active_advisor_by_id` (filtra `rol='asesor' AND estado_disponibilidad='activo'`) | `tests/unit/test_h3_3_5_advisor_service.py` | AC-17 |
| 7 | Listado `/leads` scoped a cartera | AC-6, AC-7, AC-8 | `app/services/solicitud_service.py::get_crm_bandeja` + repo `portfolio_asesor_id` | `tests/integration/test_h3_3_5_advisor_portfolio.py` (PostgreSQL real) + `tests/unit/test_h3_3_5_advisor_service.py` | AC-17 |
| 8 | `/leads/board` scoped a cartera | AC-8 | mismo flujo `get_crm_bandeja` (ruta `/leads/board`) | `tests/integration/test_h3_3_5_advisor_portfolio.py` | AC-17 |
| 9 | Búsqueda respeta cartera (server-side) | AC-8 | `_build_crm_query_filters` + `portfolio_asesor_id` | `tests/integration/test_h3_3_5_advisor_portfolio.py` | AC-17 |
| 10 | Filtros (AFP, estado, fechas, origen, fuente, sin_asignar, estancado) respetan cartera | AC-8 | `_build_crm_query_filters` | `tests/integration/test_h3_3_5_advisor_portfolio.py` | AC-17 |
| 11 | Ordenamiento respeta cartera | AC-8 | `get_crm_solicitudes` (ORDER BY dentro de la misma consulta filtrada) | `tests/integration/test_h3_3_5_advisor_portfolio.py` | AC-17 |
| 12 | Conteos respetan cartera | AC-8 | `get_crm_solicitudes` (`COUNT(*)` con el mismo `where_clause`) | `tests/integration/test_h3_3_5_advisor_portfolio.py` | AC-17 |
| 13 | Paginación respeta cartera | AC-8 | `get_crm_solicitudes` (`LIMIT/OFFSET` tras el filtro de cartera) | `tests/integration/test_h3_3_5_advisor_portfolio.py` | AC-17 |
| 14 | Detalle de lead propio | AC-6, AC-7, AC-11 | `get_solicitud_detalle_masked` (rama advisor con ownership) | `tests/integration/test_h3_3_5_advisor_portfolio.py` + `tests/unit/test_h3_3_5_advisor_service.py` | AC-17 |
| 15 | Detalle de lead ajeno / sin asignar → 404 | AC-9, AC-10 | `get_solicitud_detalle_masked` → `None`; `lead_active_assignment_belongs_to` | `tests/integration/test_h3_3_5_advisor_portfolio.py` + `tests/unit/test_h3_3_5_advisor_service.py` | AC-17 |
| 16 | Cambio de estado propio permitido / ajeno rechazado sin escribir | AC-10, AC-11 | `update_lead_status(actor=..., advisor_scope=...)` + repo ownership | `tests/integration/test_h3_3_5_advisor_portfolio.py` + `tests/integration/test_h3_3_5_advisor_http.py` | AC-17 |
| 17 | Comentarios/notas propios permitidos / ajenos rechazados | AC-10, AC-11 | `append_lead_comment(actor=..., advisor_scope=...)` + repo ownership | `tests/integration/test_h3_3_5_advisor_portfolio.py` + `tests/integration/test_h3_3_5_advisor_http.py` | AC-17 |
| 18 | Cleanup según política vigente (advisor no permitido) | AC-10 | `_CLEANUP_ROLES` (sin cambios: advisor excluido → 403) | `tests/integration/test_h3_3_5_advisor_http.py` | AC-17 |
| 19 | Asignación/reasignación siempre prohibida para advisor | AC-12 | `can_assign_lead` (sin cambios) + ruta `POST /leads/{id}/assign` 403 | `tests/integration/test_h3_3_5_advisor_http.py` + `tests/unit/test_h3_3_5_advisor_service.py` | AC-17 |
| 20 | Dashboard `/dashboard` → 403 real para advisor | AC-13 | `app/web/routes/dashboard.py::require_executive_access` (ya 403 no-superuser) | `tests/unit/test_h3_3_5_advisor_web.py` | AC-17 |
| 21 | Navegación advisor sin enlace a dashboard | AC-14 | `base.html` + `_can_view_executive_dashboard` (ya oculto no-superuser) | `tests/unit/test_h3_3_5_advisor_web.py` | AC-17 |
| 22 | PII propia completa para advisor (sin máscara) | AC-6, AC-7, D2 | `get_solicitud_detalle_masked` devuelve row completo para lead propio | `tests/unit/test_h3_3_5_advisor_service.py` | AC-17 |
| 23 | PII ajena ausente (404 / sin HTML residual) | AC-9, AC-16 | ownership + 404 + `mask_row_for_display` | `tests/unit/test_h3_3_5_advisor_service.py`, `tests/unit/test_h3_3_5_advisor_web.py` | AC-17, AC-19 |
| 24 | HTML sin residuos de PII ajena / raw_payload | AC-16 | templates + `raw_payload` nunca expuesto a advisor | `tests/unit/test_h3_3_5_advisor_web.py` | AC-19 |
| 25 | Seed DEV (Asesor Desarrollo 1/2) idempotente, no ejecutado | AC-1, AC-2, AC-18 | `scripts/sql/dev/seed_asesores_desarrollo.sql` (rol/estado explícitos, `lower(btrim(nombre))`) | `tests/integration/test_h3_3_5_seed.py` (PostgreSQL real) + `tests/unit/test_h3_3_5_seed_sql.py` (estático) | AC-19 (postflight read-only Deployer) |
| 26 | Preflight operacional del seed (STS, cuenta, región, env, endpoint, base, usuario, salud) | AC-18, D5 | `docs/H3_3_5_DEV_RUNBOOK.md` (fuentes canónicas, incluye endpoint) | `tests/unit/test_h3_3_5_seed_sql.py` | AC-19 |
| 27 | Registro preexistente: adoptar UUID único o abortar | AC-1, AC-2, AC-18, D6 | `seed_asesores_desarrollo.sql` (DO plpgsql por `lower(btrim(nombre))`, `IS DISTINCT FROM`) | `tests/integration/test_h3_3_5_seed.py` | AC-19 |
| 28 | Idempotencia (2ª ejecución = mismo resultado) | AC-18, D6 | `seed_asesores_desarrollo.sql` | `tests/integration/test_h3_3_5_seed.py` | AC-19 |
| 29 | Postflight DB read-only (Deployer) | AC-19, D3 | `docs/H3_3_5_DEV_RUNBOOK.md` sección postflight | — | AC-19 (Deployer) |
| 30 | Carga y refresh de `AUTH_USERS_JSON` | AC-21, D7 | evidencia de código en runbook (parseo en `SimpleDevAuth.__init__`; refresh humano vía `RestartAppServer`/`UpdateEnvironment`) | `tests/unit/test_h3_3_5_advisor_auth.py` | AC-17 (refresh controlado humano) |
| 31 | Orden seguro de cutover (datos → postflight → RBAC → Ready → identidades → refresh → salud → smoke) | AC-17, AC-18, D7 | `docs/H3_3_5_DEV_RUNBOOK.md` sección cutover | — | AC-17 |
| 32 | No regresión CEO/CTO | AC-15 | `is_superuser` + `can_view_full_pii` sin cambios + tests existentes | `tests/unit/test_rbac_superusers.py`, `tests/unit/test_h3_3_1_rbac_pii_assignment.py` | AC-17, AC-19 |
| 33 | Secretos ausentes de archivos/evidencias | AC-5 | sin cambios de secretos; `validate_repo.py` escanea evidencia/progress | `validate_repo.py` + escaneo de secretos | AC-19 |

## Cobertura de AC

| AC | Descripción resumida | Cobertura |
| --- | --- | --- |
| AC-1 | Asesor Desarrollo 1 único en `tpi.asesores` (crea/adopta/aborta) | seed SQL + `tests/integration/test_h3_3_5_seed.py` |
| AC-2 | Asesor Desarrollo 2 único en `tpi.asesores` (crea/adopta/aborta) | seed SQL + `tests/integration/test_h3_3_5_seed.py` |
| AC-3 | Identidad `asesor.desarrollo1` con `advisor_id` (no por nombre) | `advisor_id` + parser |
| AC-4 | Identidad `asesor.desarrollo2` con `advisor_id` (no por nombre) | `advisor_id` + parser |
| AC-5 | Contraseñas/hashes fuera del repo/PR/logs/evidencia | `validate_repo.py` + escaneo |
| AC-6 | Asesor Desarrollo 1 ve solo su cartera + PII propia | `tests/integration/test_h3_3_5_advisor_portfolio.py` + PII contextual |
| AC-7 | Asesor Desarrollo 2 ve solo su cartera + PII propia | `tests/integration/test_h3_3_5_advisor_portfolio.py` + PII contextual |
| AC-8 | Búsqueda/filtros/tablero/orden/conteo/paginación server-side | `portfolio_asesor_id` en repo + `tests/integration/test_h3_3_5_advisor_portfolio.py` |
| AC-9 | Detalle ajeno/no asignado → 404 | `lead_active_assignment_belongs_to` + `tests/integration/test_h3_3_5_advisor_portfolio.py` |
| AC-10 | Mutación ajena/no asignada rechazada sin escribir (status/comments/cleanup) | ownership en servicio/repo + `tests/integration/test_h3_3_5_advisor_http.py` |
| AC-11 | Acciones autorizadas solo sobre leads propios | ownership en servicio/repo + `tests/integration/test_h3_3_5_advisor_http.py` |
| AC-12 | Asignar/reasignar prohibido (UI oculta + 403) | `can_assign_lead` + ruta |
| AC-13 | `/dashboard` 403 real para advisor | `require_executive_access` |
| AC-14 | Menú advisor sin dashboard | `base.html` + `_can_view_executive_dashboard` |
| AC-15 | CEO/CTO sin regresión | tests superuser + RBAC |
| AC-16 | PII contextual por lead (no permiso global) | `get_solicitud_detalle_masked` ownership + `tests/integration/test_h3_3_5_advisor_portfolio.py` |
| AC-17 | Smoke AWS DEV autenticado (post-cutover) | runbook cutover + smoke |
| AC-18 | Seed idempotente + preflight operacional humano | seed SQL + `tests/integration/test_h3_3_5_seed.py` + runbook |
| AC-19 | Postflight DB read-only; STOP si falla seed | runbook + evidencia |
| AC-20 | Cobertura ≥ 85% | `pytest --cov-fail-under=85` |
| AC-21 | Vínculo fail-closed (sin/malformado/inexistente/no activo) | `resolve_advisor_identity` + parser |

## Resultado del Requirements Coverage Gate

- Estado: **PASS**
- Todo requisito listado en el enunciado tiene AC, componente previsto y prueba automatizada o
  smoke/evidencia reproducible.
- No se detectó ningún requisito sin AC, sin implementación prevista, sin prueba automatizada
  cuando corresponde o sin evidencia reproducible.
- No hay BLOCKER de cobertura.

*Gate registrado como paso de Developer (evidencia `developer.json`).*
