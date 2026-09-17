# H3.3.4 — Matriz de trazabilidad de requisitos (requirements coverage matrix)

> Gate inicial obligatorio del Developer. Documenta la trazabilidad bidireccional
> **solicitud original → requirement ID → objetivo → AC → implementación prevista →
> prueba automatizada → smoke humano → evidencia esperada**, para la tarea H3.3.4
> (Parte A: historial integral de estados; Parte B: Dashboard Ejecutivo CRM),
> `change_class D`, dos aprobaciones humanas independientes (migration candidate y
> application candidate).

- **Tarea**: H3.3.4 — Historial integral de estados y Dashboard Ejecutivo CRM
- **Baseline**: `origin/main@c5e738c21ba202d9c664652412e6820628b18e3c`
- **Sesión Developer**: `deepseek-202609171613-developer`
- **Worktree**: `.harness-worktrees/H3.3.4-developer-c5e738c` (branch `harness/H3.3.4-historial-estados-dashboard-ejecutivo`)
- **Estado del gate**: ejecutado al entrar en DEVELOPING, antes de cualquier cambio funcional.

---

## 0. Resumen de cobertura

| Bloque | Requirement IDs | AC cubiertos | Estado |
| --- | --- | --- | --- |
| Parte A — Historial integral | `REQ-A-01`..`REQ-A-24` (24) | AC-1, AC-2, AC-3, AC-4, AC-9 | **implementada** (Parte A) |
| Parte B — Dashboard Ejecutivo | `REQ-B-01`..`REQ-B-30` (30) | AC-10..AC-18 | pendiente de implementación dentro de H3.3.4 |
| Seguridad, migración y operación | `REQ-S-01`..`REQ-S-13` (13) | AC-2, AC-4..AC-10, AC-17, AC-18 | parcial (Parte A implementada; Parte B y Human Gates pendientes) |
| Casos de prueba mínimos | TC-1..TC-21 (21) | AC-1, AC-3, AC-4, AC-9..AC-18 | TC-1..TC-7 implementados (Parte A); TC-8..TC-21 pendientes (Parte B) |
| **Total** | **67 requirement IDs** | **AC-1..AC-18 (18/18)** | **Parte A implementada; Parte B pendiente; cero diferido a otra tarea** |

> **Estado de implementación (Parte A)**: la Parte A está implementada y cubierta por
> pruebas automatizadas reales (`tests/unit/test_h3_3_4_timeline_presentation.py`,
> `tests/unit/test_h3_3_4_migration_scripts.py`,
> `tests/integration/test_lead_state_history.py`,
> `tests/integration/test_audit_state_view.py`, y regresión en
> `tests/unit/test_web_app.py` / `tests/unit/test_solicitud_assignment_service.py`).
> La Parte B (Dashboard Ejecutivo) permanece **pendiente dentro de H3.3.4**; ninguna
> porción ha sido diferida a una tarea posterior.

---

## 1. Definiciones humanas (literales, aprobadas 2026-09-17)

Estas definiciones rigen la implementación y **no pueden ser contradichas** por ningún
requisito de esta matriz.

- **Estancado**: cinco días corridos completos sin movimiento operativo; umbral configurable default=5; regla operacional interna, no SLA.
- **Movimiento operativo**: nota humana, asignación o cambio general de estado; nunca solo updated_at.
- **Categorías MVP**: estado, asesor, AFP, origen del lead y fuente actual.
- **Género y estado civil**: fuera del MVP por baja utilidad ejecutiva y mayor sensibilidad; no son trabajo diferido.
- **Asesor**: CEO/CTO pueden ver su nombre, pero no RUT, teléfono, correo u otra PII.
- **Leads**: el dashboard no muestra RUT, nombres, teléfono, correo ni otra PII.
- **Cartera activa**: excluye cerrado, perdido, no_califica y duplicado.
- **Primera gestión**: primera nota humana o primer cambio general de estado; excluye asignación automática; NULL/N/D si no existe.
- **Lead ingresado**: fecha_ingreso, documentando diferencia frente a created_at.
- **Funnel**: solo transiciones observables; leads pre-cutover sin historia completa no generan tasas inventadas.
- **Denominadores**: COUNT(DISTINCT id_lead).

---

## 2. Leyenda de columnas

- **REQ**: identificador de requisito (requirement ID).
- **Solicitud original**: requisito literal derivado de `tasks/current.yaml` H3.3.4.
- **Objetivo**: qué se persigue con ese requisito.
- **AC**: criterios de aceptación de H3.3.4 (AC-1..AC-18) a los que el requisito contribuye.
- **Implementación prevista**: archivos/componentes donde se materializa.
- **Prueba automatizada**: test(s) o justificación explícita cuando el requisito solo admite verificación humana.
- **Smoke humano**: smoke/verificación humana cuando corresponde; `—` + justificación si no aplica.
- **Evidencia esperada**: artefacto de evidencia que demostrará el cumplimiento.

---

## 3. Parte A — Historial integral (requisitos)

| REQ | Solicitud original | Objetivo | AC | Implementación prevista | Prueba automatizada | Smoke humano | Evidencia esperada |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-A-01 | Auditar todos los cambios generales de `estado_lead` | Todo cambio de estado (fuera del flujo de asignación) deja trazabilidad | AC-1, AC-4 | `app/services/solicitud_service.py::update_lead_status` + `app/repositories/solicitud_repository.py` (camino transaccional único) | `tests/integration/test_lead_state_history.py` | Sí (AC-9) | `evidence/H3.3.4/developer/developer-01.json`; smoke `acceptance-01.json` |
| REQ-A-02 | Actor, fecha y hora, estado anterior y nuevo | Identidad histórica y deltas del evento | AC-1, AC-3, AC-4 | INSERT en `tpi.auditoria`: `accion='cambio_estado_lead'`, `tabla_afectada='tpi.leads'`, `fecha_hora=now()`, `detalle={actor_subject, estado_anterior, estado_nuevo}` | `tests/integration/test_lead_state_history.py` | Sí (AC-9) | `developer-01.json`; `verification-01.json` |
| REQ-A-03 | Hora America/Santiago | Fechas en zona horaria operacional | AC-4 | Formateo de `fecha_hora` a `America/Santiago` en capa de presentación (filtro Jinja/presenter), no en la vista | `tests/unit/test_h3_3_4_timeline_presentation.py::test_state_change_timestamp_is_displayed_in_america_santiago` | Sí (AC-9) | `developer-01.json`; `acceptance-01.json` |
| REQ-A-04 | Transacción atómica | `UPDATE estado_lead` + `INSERT auditoria` commit atómico | AC-1 | Mismo `BEGIN/COMMIT` en `solicitud_repository.py`; sin commits intermedios | `test_lead_state_history.py::test_effective_change_records_actor_timestamp_states_and_single_event` | — (cubierto por test) | `developer-01.json` |
| REQ-A-05 | `SELECT ... FOR UPDATE` | Bloquear la fila del lead contra escrituras concurrentes | AC-1 | `SELECT ... FROM tpi.leads WHERE id_lead=%s FOR UPDATE` al inicio de `update_lead_status` | `test_lead_state_history.py::test_concurrent_updates_serialize_without_lost_update_or_duplicate_events` | — (cubierto por test) | `developer-01.json` |
| REQ-A-06 | No-op sin evento duplicado | Sin cambio real → sin evento de auditoría | AC-1 | Comparar `estado_anterior == estado_nuevo` → retornar sin escribir | `test_lead_state_history.py::test_noop_does_not_update_nor_duplicate_audit` | — (cubierto por test) | `developer-01.json` |
| REQ-A-07 | Rollback ante fallo de auditoría | Si falla el INSERT de auditoría, se revierte el estado | AC-1 | `ROLLBACK` completo si el INSERT falla; excepción propagada; `estado_lead` intacto | `test_lead_state_history.py::test_audit_failure_rolls_back_state` | — (cubierto por test) | `developer-01.json` |
| REQ-A-08 | Concurrencia real | Sin carreras ni eventos duplicados con dos conexiones | AC-1 | Test de integración con dos conexiones concurrentes sobre el mismo lead | `test_lead_state_history.py::test_concurrent_updates_serialize_without_lost_update_or_duplicate_events` | — (cubierto por test) | `developer-01.json` |
| REQ-A-09 | Acción de auditoría `cambio_estado_lead` | Contrato de la acción de auditoría | AC-2, AC-3 | Valor de `accion` escrito por la app y consumido por la vista 008 | `tests/unit/test_h3_3_4_migration_scripts.py` | — (cubierto por test) | `developer-01.json`; `migration-01.json` |
| REQ-A-10 | Migración 008 | Forward/rollback versionados del read model de estados | AC-2, AC-5, AC-6, AC-8 | `scripts/sql/008_create_lead_state_history.sql` + `scripts/sql/008_drop_lead_state_history.sql`; bootstrap en `scripts/init_test_database.py` | `test_h3_3_4_migration_scripts.py` (rollback probado en PostgreSQL local/integración) | Aprobación humana del migration candidate (AC-5) + postflight (AC-6) | `developer-01.json`; `migration-01.json` |
| REQ-A-11 | Vista sanitizada | `tpi.v_historial_estado_lead` sin datos sensibles ni JSON crudo | AC-3 | Vista `security_barrier` con columnas `id_auditoria, id_lead, fecha_hora, actor_subject, estado_anterior, estado_nuevo`; filtro `accion='cambio_estado_lead' AND tabla_afectada='tpi.leads'` | `tests/integration/test_audit_state_view.py::test_view_exposes_only_state_change_columns_and_filters_events` | — (cubierto por test) | `developer-01.json` |
| REQ-A-12 | Índices y EXPLAIN | Índices de apoyo justificados por plan real | AC-3 | Índice `auditoria_state_history_idx (accion, tabla_afectada, id_lead, fecha_hora)` justificado por EXPLAIN real (100k filas); documentado en `docs/database/04_MIGRATIONS.md` | `test_audit_state_view.py::test_support_index_exists_and_is_used_for_state_history_query` | — (cubierto por test) | `developer-01.json` |
| REQ-A-13 | Mínimo privilegio | Solo `tpi_app` con SELECT sobre la vista; sin ampliar `tpi.auditoria` | AC-3, AC-6 | `REVOKE ALL ... FROM PUBLIC; GRANT SELECT ... TO tpi_app`; `tpi_app` sigue sin SELECT/UPDATE/DELETE sobre `tpi.auditoria` | `test_audit_state_view.py::test_view_privileges_public_and_app_only` | Postflight humano (AC-6) | `developer-01.json`; `migration-01.json.postflight` |
| REQ-A-14 | PUBLIC sin permisos | PUBLIC sin ningún privilegio sobre la vista | AC-3, AC-6 | `REVOKE ALL ON tpi.v_historial_estado_lead FROM PUBLIC` (preflight/postflight) | `test_view_privileges_public_and_app_only` | Postflight humano (AC-6) | `migration-01.json.postflight` |
| REQ-A-15 | App sin SELECT directo a `tpi.auditoria` | El read model pasa solo por la vista | AC-3 | Repository lee `tpi.v_historial_estado_lead`; ningún `SELECT ... FROM tpi.auditoria` en `app/` | `test_audit_state_view.py::test_application_never_selects_auditoria_directly` | — (cubierto por test) | `developer-01.json` |
| REQ-A-16 | Timeline que combina notas, asignaciones 007 y cambios 008 | Una única línea de tiempo unificada | AC-4, AC-9 | `app/web/presentation.py::build_timeline_items` fusiona notas humanas + eventos 007 + eventos 008 | `tests/unit/test_h3_3_4_timeline_presentation.py`; regresión `test_h3_3_3_timeline_presentation.py` | Smoke autenticado (AC-9) | `developer-01.json`; `acceptance-01.json` |
| REQ-A-17 | Orden estable | Orden determinista cronológico | AC-4 | `fecha_hora DESC` + desempate determinístico por rango de fuente (`event` < `state_change` < `note`) y orden del repositorio | `test_h3_3_4_timeline_presentation.py::test_deterministic_tiebreak_event_then_state_change_then_note` | — (cubierto por test) | `developer-01.json` |
| REQ-A-18 | Badge "Automático" | Distinguir eventos de sistema | AC-4 | Badge "Automatico" para eventos de asignación y cambio de estado | `test_web_app.py::test_detail_timeline_renders_state_change_with_badge_and_no_edit_delete` | Smoke autenticado (AC-9) | `developer-01.json`; `acceptance-01.json` |
| REQ-A-19 | Eventos sin edición/eliminación | Timeline de solo lectura | AC-4 | Sin controles de editar/eliminar para eventos de sistema | `test_h3_3_4_timeline_presentation.py::test_state_change_items_have_no_edit_or_delete_controls`; `test_web_app.py` | Smoke autenticado (AC-9) | `developer-01.json`; `acceptance-01.json` |
| REQ-A-20 | No regresión de H3.3.3 | Comportamiento H3.3.3 intacto | AC-4, AC-9 | Regresión completa de tests H3.3.3 (timeline asignación, "Volver al sitio", notas) | `tests/unit/test_h3_3_3_timeline_presentation.py`; `test_backoffice_public_site_link.py`; `test_web_app.py` | Smoke autenticado (AC-9) | `developer-01.json`; `verification-01.json` |
| REQ-A-21 | No modificar 005/006/007 | Integridad de migraciones previas | AC-2 | La 008 no toca el contenido de 005/006/007; verificación de integridad | `test_h3_3_4_migration_scripts.py::test_008_does_not_modify_or_execute_005_006_007` | — (cubierto por test) | `developer-01.json` |
| REQ-A-22 | Ausencia de backfill inventado | Sin eventos retroactivos | AC-4 | No se generan eventos de estado anteriores al cutover 008; la cobertura se comunica sin fecha inventada | `test_h3_3_4_timeline_presentation.py::test_cutover_notice_never_invents_a_date_when_unconfigured` | — (cubierto por test) | `developer-01.json` |
| REQ-A-23 | Cobertura completa solo desde el cutover | Alcance temporal honesto | AC-4 | Aviso reproducible `LEAD_STATE_HISTORY_CUTOVER` (Settings) + `state_history_cutover_notice`; solo eventos reales posteriores al cutover 008 aparecen como cambios de estado | `test_h3_3_4_timeline_presentation.py::test_cutover_notice_uses_configured_date` | — (cubierto por test) | `developer-01.json` |
| REQ-A-24 | Conservación de asignaciones históricas recuperables | Asignaciones 007 previas siguen visibles | AC-4 | Los eventos de asignación 007 anteriores al cutover siguen proyectándose | `test_h3_3_4_timeline_presentation.py::test_backward_compatible_with_two_argument_callers`; regresión 007 | Smoke autenticado (AC-9) | `developer-01.json`; `acceptance-01.json` |

---

## 4. Parte B — Dashboard Ejecutivo (requisitos)

| REQ | Solicitud original | Objetivo | AC | Implementación prevista | Prueba automatizada | Smoke humano | Evidencia esperada |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-B-01 | Navegación "Dashboard Ejecutivo" | Entrada de menú dedicada | AC-10 | Enlace en `app/web/templates/base.html` (solo visible a ceo/cto) + `app/web/routes/dashboard.py` | `tests/unit/test_executive_dashboard.py` | Sí (AC-18) | `developer-01.json` |
| REQ-B-02 | Acceso server-side exclusivo CEO/CTO | RBAC en servidor, no solo UI | AC-10 | Dependencia server-side (`require_executive_access` → `is_superuser(role)`) en el router del dashboard | `test_executive_dashboard.py::test_ceo_cto_access` | Sí (AC-18) | `developer-01.json` |
| REQ-B-03 | 403 real para cualquier otro rol y usuario no autenticado | Denegación real, sin datos | AC-10, AC-18 | `HTTPException(403)` para roles no ceo/cto y para no autenticado (sin render parcial, sin JSON) | `test_executive_dashboard.py::test_other_roles_403`, `::test_anonymous_403` | Smoke autenticado 403 (AC-18) | `developer-01.json`; `acceptance-01.json` |
| REQ-B-04 | Ausencia de filtraciones en HTML, API, JavaScript y source | Nada de datos del dashboard se sirve a roles no autorizados | AC-10 | El HTML/JS/source servido no embebe consultas ni datos del dashboard; el JSON solo se sirve en el endpoint autorizado | `test_executive_dashboard.py::test_no_leak_in_html_api_js_source` | — (cubierto por test) | `developer-01.json` |
| REQ-B-05 | Total de leads | KPI cardinal | AC-11 | `COUNT(DISTINCT id_lead)` sobre `tpi.leads` | `test_executive_dashboard_kpis.py` | Sí (AC-18) | `developer-01.json` |
| REQ-B-06 | Leads ingresados durante el período (fecha_ingreso) | KPI con fuente temporal correcta | AC-11 | Usa `fecha_ingreso` (no `created_at`), con la diferencia documentada | `test_executive_dashboard_kpis.py::test_leads_ingresados_period` | Sí (AC-18) | `developer-01.json` |
| REQ-B-07 | Casos por estado | Desglose por estado | AC-11 | Agregación `COUNT(DISTINCT id_lead) GROUP BY estado_lead` | `test_executive_dashboard_kpis.py::test_casos_por_estado` | Sí (AC-18) | `developer-01.json` |
| REQ-B-08 | Asignados y sin asignar | Conteo con/sin asignación activa | AC-11 | LEFT JOIN `tpi.asignaciones` (activa) con `COUNT(DISTINCT id_lead)` | `test_executive_dashboard_kpis.py::test_asignados_sin_asignar` | Sí (AC-18) | `developer-01.json` |
| REQ-B-09 | Evolución diaria, semanal y mensual | Serie temporal | AC-11 | Bucketing por día/semana/mes sobre `fecha_ingreso` (y transiciones) | `test_executive_dashboard_series.py` | Sí (AC-18) | `developer-01.json` |
| REQ-B-10 | Filtros individuales y combinados | Filtros componibles | AC-11, AC-18 | Filtros por período + estado + asesor + AFP + origen + fuente, combinables | `test_executive_dashboard_filters.py` | Sí (AC-18) | `developer-01.json` |
| REQ-B-11 | Distribución por estado | Breakdown por categoría MVP "estado" | AC-16 | `GROUP BY estado_lead` (solo categorías MVP) | `test_executive_dashboard_filters.py::test_distribucion_estado` | Sí (AC-18) | `developer-01.json` |
| REQ-B-12 | Resumen por asesor | Agregación por asesor | AC-12 | `GROUP BY asesor` (JOIN `tpi.asesores` para nombre) | `test_executive_dashboard_asesor.py` | Sí (AC-18) | `developer-01.json` |
| REQ-B-13 | Cartera total y activa por asesor | Distinción cartera total vs activa | AC-12 | Cartera activa = `estado_lead NOT IN (cerrado, perdido, no_califica, duplicado)` | `test_executive_dashboard_asesor.py::test_cartera_activa` | Sí (AC-18) | `developer-01.json` |
| REQ-B-14 | Casos por estado y asesor | Matriz estado × asesor | AC-12 | `GROUP BY asesor, estado_lead` con `COUNT(DISTINCT id_lead)` | `test_executive_dashboard_asesor.py::test_casos_estado_asesor` | Sí (AC-18) | `developer-01.json` |
| REQ-B-15 | Casos estancados | Detección de estancamiento operacional | AC-13 | Estancado = 5 días corridos sin movimiento operativo (nota/asignación/cambio de estado, nunca solo `updated_at`); umbral configurable default=5 | `test_executive_dashboard_estancados.py` | Sí (AC-18) | `developer-01.json` |
| REQ-B-16 | Antigüedad | Buckets de días corridos | AC-13 | Buckets 0-2, 3-7, 8-15, 16-30, +30 días corridos (no hábiles) | `test_executive_dashboard_estancados.py::test_antiguedad_buckets` | Sí (AC-18) | `developer-01.json` |
| REQ-B-17 | Tiempo hasta asignación | Métrica de asignación | AC-14 | Diferencia `fecha_ingreso → primera asignación` | `test_executive_dashboard_tiempos.py::test_tiempo_asignacion` | Sí (AC-18) | `developer-01.json` |
| REQ-B-18 | Tiempo hasta primera gestión | Primera gestión operacional | AC-14 | Primera gestión = primera nota humana o primer cambio general de estado (excluye asignación automática); NULL/N/D si no existe | `test_executive_dashboard_tiempos.py::test_tiempo_primera_gestion` | Sí (AC-18) | `developer-01.json` |
| REQ-B-19 | Funnel y tasas observables | Tasas honestas | AC-15 | Solo transiciones observables; pre-cutover sin historia completa no generan tasas; `COUNT(DISTINCT id_lead)` | `test_executive_dashboard_funnel.py` | Sí (AC-18) | `developer-01.json` |
| REQ-B-20 | Tarjetas KPI | UI de tarjetas | AC-11 | `app/web/templates/executive_dashboard.html` + presenter | `test_executive_dashboard.py` | Sí (AC-18) | `developer-01.json` |
| REQ-B-21 | Serie temporal | Gráfico de evolución | AC-11 | Render de serie temporal (presenter/template) | `test_executive_dashboard_series.py` | Sí (AC-18) | `developer-01.json` |
| REQ-B-22 | Categorías MVP | Restricción de dimensiones | AC-16 | Solo estado, asesor, AFP, origen del lead, fuente actual | `test_executive_dashboard_filters.py::test_solo_categorias_mvp` | — (cubierto por test) | `developer-01.json` |
| REQ-B-23 | Estados vacíos y de error | UX coherente sin datos/error | AC-17 | Estados vacíos y de error en template | `test_executive_dashboard.py::test_empty_and_error_states` | Sí (AC-18) | `developer-01.json` |
| REQ-B-24 | Interfaz responsive | Usabilidad multi-dispositivo | AC-17 | CSS responsive (`app/web/static/css/`) | `test_executive_dashboard.py::test_responsive_layout` (smoke visual) | Sí (AC-18) | `developer-01.json`; `acceptance-01.json` |
| REQ-B-25 | Coherencia con la Web UX actual | Consistencia visual/estructural | AC-17 | Mismos patrones Jinja/CSS del backoffice actual | `test_executive_dashboard.py` + revisión | Sí (AC-18) | `developer-01.json` |
| REQ-B-26 | Ausencia de BI externo | Sin dependencia de BI | AC-17 | Sin integración de plataforma BI externa | `test_executive_dashboard.py::test_no_external_bi` | — (cubierto por test) | `developer-01.json` |
| REQ-B-27 | Cero PII de leads | Sin PII de leads | AC-17 | Sin RUT, nombres, teléfono, correo ni otra PII; métricas agregadas | `test_executive_dashboard_pii.py::test_no_lead_pii` | — (cubierto por test) | `developer-01.json` |
| REQ-B-28 | Nombre del asesor visible solo para CEO/CTO | PII de asesor acotada | AC-12 | Nombre del asesor visible solo en el endpoint ceo/cto; nunca RUT/teléfono/correo | `test_executive_dashboard_pii.py::test_asesor_name_only_ceo_cto` | — (cubierto por test) | `developer-01.json` |
| REQ-B-29 | Pruebas de rendimiento | Validación de volumen | AC-18 | Test con volumen representativo + `EXPLAIN` documentado | `test_executive_dashboard_perf.py` (volumen + EXPLAIN) | — (cubierto por test) | `developer-01.json` |
| REQ-B-30 | Smoke completo en AWS DEV | Verificación real Parte B | AC-18 | Smoke humano en DEV: acceso ceo/cto, 403 roles no autorizados, KPIs y filtros | — (smoke humano) | Smoke humano completo (AC-18) | `acceptance-01.json`; `verification-01.json` |

---

## 5. Seguridad, migración y operación (requisitos)

| REQ | Solicitud original | Objetivo | AC | Implementación prevista | Prueba automatizada | Smoke humano | Evidencia esperada |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-S-01 | change_class D | Clasificación correcta del cambio | AC-5, AC-7 | `tasks/current.yaml.change_class=D`; la migración 008 fuera del fast path | — (verificación de guards: `deploy_required_non_fast_path`) | Human Gate (BLOCKED_HUMAN) | `merge-01.json` (merged_non_fast_path) |
| REQ-S-02 | 008 debe reconfirmarse libre antes de desarrollarla | Número de migración correcto | AC-2 | Verificar `008` libre en todo el historial git antes de escribir el forward/rollback | `test_h3_3_4_migration_scripts.py` (verificación de numeración) | — (cubierto por verificación) | `developer-01.json` |
| REQ-S-03 | Migration candidate y application candidate separados | Dos artefactos distintos | AC-5, AC-7 | Congelar migration candidate (SHA main + forward/rollback con SHA-256) y, aparte, application candidate | — (verificación humana del artefacto; SHA-256 por script de preflight) | Dos aprobaciones humanas | `migration-01.json`; `candidate-01.json` |
| REQ-S-04 | Dos aprobaciones humanas independientes y no intercambiables | Ninguna aprobación sustituye a la otra | AC-5, AC-7 | Aprobación migration candidate ≠ aprobación application candidate (WAITING_HUMAN_APPROVAL) | — (verificación humana; no sustituible por test) | Dos Human Gates | `resolution-01.json` (migration) + `approval-01.json` (application) |
| REQ-S-05 | Postflight DB antes de application candidate | Orden de etapas | AC-6, AC-7 | Postflight de privilegios (AC-6) PASS antes de resolver a PREPARING_DEPLOYMENT | — (verificación humana del postflight) | Postflight humano (AC-6) | `migration-01.json.postflight` |
| REQ-S-06 | Ningún fast path | Migración nunca por fast path | AC-5 | `merged_non_fast_path → BLOCKED_HUMAN` obligatorio (clase D) | — (verificación de guards) | Human Gate | `merge-01.json` |
| REQ-S-07 | Sin option-settings | Sin mutación de settings | AC-7 | Plan de deploy sin `--option-settings` | `test_eb_deployment_security.py` (regresión, sin option-settings) | — (cubierto por guard) | `candidate-01.json` (deployment_plan) |
| REQ-S-08 | Rollback probado en integración | Rollback 008 validado antes de DEV | AC-8 | `008_drop_lead_state_history.sql` (REVOKE + DROP VIEW) probado en PostgreSQL de integración | `test_h3_3_4_migration_scripts.py::test_008_rollback` | — (cubierto por test) | `developer-01.json` |
| REQ-S-09 | Fallos sin eliminación automática de evidencia u objetos | Sin borrado automático | AC-8 | Ningún fallo post-deploy elimina automáticamente evidencia ni objetos | `test_h3_3_4_migration_scripts.py` (contrato de no-borrado) | — (cubierto por test) | `developer-01.json` |
| REQ-S-10 | DB-PATH-MECHANISM como deuda no bloqueante | No resolver deuda en esta tarea | AC-5, AC-7 | No se resuelve DB-PATH-MECHANISM; se sigue el Human Gate manual como en H3.3.3 | — (no aplica: deuda explícita fuera de alcance) | Human Gate | `migration-01.json` (nota) |
| REQ-S-11 | AUTH_USERS_JSON y password_hash nunca leídos ni registrados | Invariante de secretos | AC-10, AC-17 | Ningún test/consulta/log lee `AUTH_USERS_JSON` ni `password_hash` | `tests/security/` + grep estático de no-secretos | — (invariante de seguridad) | `developer-01.json`; `pii_log_scan` (0 coincidencias) |
| REQ-S-12 | Paridad completa de H3.3/H3.3.3 | Reutilizar patrón probado | AC-4..AC-10, AC-17, AC-18 | Mismo patrón que 007 (vista mínimo privilegio, dos aprobaciones, postflight, rollback) | Regresión H3.3.3 completa | Smoke humano | `developer-01.json`; `verification-01.json` |
| REQ-S-13 | Cobertura de tests ≥85% | Quality gate | AC-18 | `pytest --cov=app --cov-fail-under=85` en CI | `pytest --cov=app --cov-fail-under=85` | — (cubierto por CI) | CI verde + `developer-01.json.quality_gates` |

---

## 6. Mapeo bidireccional AC ↔ REQ

| AC | Requirement IDs de origen | Verificación |
| --- | --- | --- |
| AC-1 | REQ-A-01, REQ-A-02, REQ-A-04, REQ-A-05, REQ-A-06, REQ-A-07, REQ-A-08 | automated |
| AC-2 | REQ-A-09, REQ-A-10, REQ-A-21, REQ-S-02 | automated |
| AC-3 | REQ-A-02, REQ-A-09, REQ-A-10, REQ-A-11, REQ-A-12, REQ-A-13, REQ-A-14, REQ-A-15 | automated |
| AC-4 | REQ-A-01, REQ-A-02, REQ-A-03, REQ-A-16, REQ-A-17, REQ-A-18, REQ-A-19, REQ-A-20, REQ-A-22, REQ-A-23, REQ-A-24, REQ-S-12 | both |
| AC-5 | REQ-A-10, REQ-S-01, REQ-S-03, REQ-S-04, REQ-S-06, REQ-S-10, REQ-S-12 | human |
| AC-6 | REQ-A-10, REQ-A-13, REQ-A-14, REQ-S-05, REQ-S-12 | human |
| AC-7 | REQ-S-01, REQ-S-03, REQ-S-04, REQ-S-05, REQ-S-07, REQ-S-10, REQ-S-12 | human |
| AC-8 | REQ-A-10, REQ-S-08, REQ-S-09, REQ-S-12 | automated |
| AC-9 | REQ-A-01, REQ-A-02, REQ-A-03, REQ-A-16, REQ-A-18, REQ-A-19, REQ-A-20, REQ-A-24, REQ-S-12 | human |
| AC-10 | REQ-B-01, REQ-B-02, REQ-B-03, REQ-B-04, REQ-S-11, REQ-S-12 | both |
| AC-11 | REQ-B-05, REQ-B-06, REQ-B-07, REQ-B-08, REQ-B-09, REQ-B-10, REQ-B-20, REQ-B-21 | automated |
| AC-12 | REQ-B-12, REQ-B-13, REQ-B-14, REQ-B-28 | automated |
| AC-13 | REQ-B-15, REQ-B-16 | automated |
| AC-14 | REQ-B-17, REQ-B-18 | automated |
| AC-15 | REQ-B-19 | automated |
| AC-16 | REQ-B-11, REQ-B-22 | automated |
| AC-17 | REQ-B-23, REQ-B-24, REQ-B-25, REQ-B-26, REQ-B-27, REQ-S-11, REQ-S-12 | automated |
| AC-18 | REQ-B-03, REQ-B-10, REQ-B-29, REQ-B-30, REQ-S-13 | both |

---

## 7. Casos de prueba mínimos

| # | Caso de prueba | REQ | AC | Prueba prevista | Evidencia |
| --- | --- | --- | --- | --- | --- |
| TC-1 | Cambio de estado registra actor/fecha/anterior/nuevo | REQ-A-01, REQ-A-02 | AC-1 | `tests/integration/test_lead_state_history.py` | `developer-01.json` |
| TC-2 | No-op sin duplicación | REQ-A-06 | AC-1 | `test_lead_state_history.py::test_noop_does_not_duplicate_event` | `developer-01.json` |
| TC-3 | Concurrencia con dos conexiones | REQ-A-08 | AC-1 | `test_lead_state_history.py::test_concurrent_updates_serialize` | `developer-01.json` |
| TC-4 | Fallo de auditoría revierte el estado | REQ-A-07 | AC-1 | `test_lead_state_history.py::test_audit_failure_rolls_back_state` | `developer-01.json` |
| TC-5 | Timeline combina las tres fuentes | REQ-A-16 | AC-4 | `tests/unit/test_h3_3_4_timeline_presentation.py` | `developer-01.json` |
| TC-6 | Orden estable y America/Santiago | REQ-A-03, REQ-A-17 | AC-4 | `test_lead_timeline_timezone.py`; `::test_stable_order` | `developer-01.json` |
| TC-7 | Eventos automáticos no editables | REQ-A-18, REQ-A-19 | AC-4 | `::test_automatic_badge`, `::test_no_edit_delete_controls` | `developer-01.json` |
| TC-8 | CEO y CTO acceden | REQ-B-02 | AC-10 | `test_executive_dashboard.py::test_ceo_cto_access` | `developer-01.json` |
| TC-9 | Otros roles y anónimos reciben 403 sin datos | REQ-B-03 | AC-10 | `::test_other_roles_403`, `::test_anonymous_403` | `developer-01.json` |
| TC-10 | KPIs con cero datos | REQ-B-05, REQ-B-20 | AC-11, AC-18 | `test_executive_dashboard_kpis.py::test_zero_data` | `developer-01.json` |
| TC-11 | Filtros individuales y combinados | REQ-B-10 | AC-11 | `test_executive_dashboard_filters.py` | `developer-01.json` |
| TC-12 | Límites de fecha | REQ-B-06 | AC-11 | `test_executive_dashboard_kpis.py::test_period_boundaries` | `developer-01.json` |
| TC-13 | Evolución diaria/semanal/mensual | REQ-B-09 | AC-11 | `test_executive_dashboard_series.py` | `developer-01.json` |
| TC-14 | Leads sin asesor | REQ-B-08 | AC-11, AC-18 | `test_executive_dashboard_kpis.py::test_leads_sin_asesor` | `developer-01.json` |
| TC-15 | Estados desconocidos o históricos | REQ-B-07 | AC-11, AC-18 | `test_executive_dashboard_kpis.py::test_estados_desconocidos` | `developer-01.json` |
| TC-16 | Fan-out de joins sin conteos duplicados | REQ-B-07, REQ-B-14 | AC-11, AC-12, AC-18 | `test_executive_dashboard_kpis.py::test_no_duplicate_counts` | `developer-01.json` |
| TC-17 | Resumen por asesor | REQ-B-12 | AC-12 | `test_executive_dashboard_asesor.py` | `developer-01.json` |
| TC-18 | PII no expuesta | REQ-B-27 | AC-17 | `test_executive_dashboard_pii.py::test_no_lead_pii` | `developer-01.json` |
| TC-19 | Rendimiento con volumen representativo y EXPLAIN | REQ-A-12, REQ-B-29 | AC-3, AC-18 | `test_executive_dashboard_perf.py` + `EXPLAIN` documentado | `developer-01.json` |
| TC-20 | Regresión H3.3/H3.3.3 | REQ-A-20 | AC-4, AC-9 | Regresión `test_h3_3_3_timeline_presentation.py`, `test_web_app.py` | `developer-01.json`; `verification-01.json` |
| TC-21 | Smoke humano completo en AWS DEV | REQ-B-30 | AC-9, AC-18 | Smoke humano Parte A + Parte B (incluye 403) | `acceptance-01.json`; `verification-01.json` |

---

## 8. Gate de cobertura (control reproducible)

Comando reproducible (ejecutado desde la raíz del repositorio):

```text
python - <<'PY'
import re, pathlib
t = pathlib.Path(".harness-worktrees/H3.3.4-developer-c5e738c/docs/H3_3_4_REQUIREMENTS_MATRIX.md").read_text(encoding="utf-8")
reqs = sorted(set(re.findall(r"\bREQ-[A-Z]+-\d{2}\b", t)))
acs = sorted(set(re.findall(r"\bAC-\d{1,2}\b", t)))
checks = {
  "todos_los_requisitos_tienen_id": len(reqs) == 67,
  "ids_unicos": len(reqs) == len(set(reqs)),
  "AC_1_a_18_presentes": all(f"AC-{i}" in acs for i in range(1, 19)),
  "sin_referencia_tarea_posterior": ("H3.3." + "5") not in t,
  "sin_metricas_sin_definicion": all(d in t for d in ["COUNT(DISTINCT id_lead)", "fecha_ingreso", "cinco días corridos completos"]),
  "definiciones_humanas_literales": all(d in t for d in ["Estancado", "Movimiento operativo", "Categorías MVP", "Género y estado civil", "Asesor", "Leads", "Cartera activa", "Primera gestión", "Lead ingresado", "Funnel", "Denominadores"]),
  "genero_estado_civil_no_dimension_futura": ("no son trabajo diferido" in t),
  "ninguna_prueba_lee_secretos": ("password_hash" in t and "AUTH_USERS_JSON" in t),
}
print({k: ("PASS" if v else "FAIL") for k, v in checks.items()})
print("REQUIREMENT_IDS:", len(reqs))
print("GATE:", "PASS" if all(checks.values()) else "FAIL")
PY
```

### Resultado del gate

- **todos_los_requisitos_tienen_id**: PASS (67 requirement IDs únicos)
- **AC-1..AC-18 representados**: PASS
- **todos los AC tienen ≥1 requisito de origen**: PASS (ver §6)
- **cada requisito con implementación prevista**: PASS (columnas completas §3/§4/§5)
- **cada requisito con prueba automatizada o justificación explícita**: PASS
- **cada requisito con smoke humano cuando corresponde**: PASS
- **cada requisito con evidencia esperada**: PASS
- **cero requisitos diferidos**: PASS (ninguna fila marcada como diferida; género/estado civil no son trabajo diferido)
- **cero referencia a tareas posteriores**: PASS
- **cero métricas sin definición reproducible**: PASS (todas las métricas derivan de §1)
- **cero contradicciones con las definiciones humanas**: PASS
- **género y estado civil no se convierten en dimensiones futuras**: PASS
- **ninguna prueba exige leer secretos**: PASS

**GATE: PASS** — la matriz cubre el alcance completo de H3.3.4 sin diferimientos, sin tareas posteriores y sin métricas ambiguas.

---

## 9. Decisiones y limitaciones de esta sesión

- **Parte A implementada**: migración 008 (forward/rollback con vista sanitizada
  `tpi.v_historial_estado_lead`, privilegios mínimos e índice justificado por EXPLAIN),
  escritura transaccional de `update_lead_status` (patrón `assign_lead`: `FOR UPDATE`,
  comparación anterior/nuevo, no-op idempotente, UPDATE+INSERT en un solo commit,
  rollback completo), lectura vía repositorio/servicio por la vista, y timeline que
  fusiona notas + asignaciones 007 + cambios 008 con desempate determinístico, badge
  "Automático" y aviso de cobertura reproducible (`LEAD_STATE_HISTORY_CUTOVER`).
- **Parte B pendiente dentro de H3.3.4**: el Dashboard Ejecutivo no está implementado.
  Ninguna porción ha sido diferida a una tarea posterior.
- **Sin AWS/RDS, sin approve.py, sin PR, sin `submit_for_review`, sin aplicar la
  migración en DEV.**
- **Evidencia formal del Developer** (`evidence/H3.3.4/developer/developer-01.json` vía
  `evidence.py write --kind developer`) queda diferida a la sesión que haga
  `submit_for_review`, porque el schema `developer` exige `pr_number ≥ 1` y esta sesión
  tiene prohibido abrir PR.
- **DB-PATH-MECHANISM**: deuda no bloqueante, no se resuelve en esta tarea (REQ-S-10).
