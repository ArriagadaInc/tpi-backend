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
| Parte B — Dashboard Ejecutivo | `REQ-B-01`..`REQ-B-30` (30) | AC-10..AC-18 | **implementada** (capa de datos + interfaz productiva); smoke humano pendiente (REQ-B-30) |
| Seguridad, migración y operación | `REQ-S-01`..`REQ-S-13` (13) | AC-2, AC-4..AC-10, AC-17, AC-18 | parcial (Parte A + Parte B implementadas; Human Gates pendientes) |
| Casos de prueba mínimos | TC-1..TC-21 (21) | AC-1, AC-3, AC-4, AC-9..AC-18 | TC-1..TC-20 implementados; TC-21 (smoke humano) pendiente |
| **Total** | **67 requirement IDs** | **AC-1..AC-18 (18/18)** | **Parte A + Parte B implementadas; pendientes solo los criterios de verificación humana; cero diferido a otra tarea** |

> **Estado de implementación**: la Parte A está implementada y cubierta por pruebas
> automatizadas reales (`tests/unit/test_h3_3_4_timeline_presentation.py`,
> `tests/unit/test_h3_3_4_migration_scripts.py`,
> `tests/integration/test_lead_state_history.py`,
> `tests/integration/test_audit_state_view.py`, y regresión en
> `tests/unit/test_web_app.py` / `tests/unit/test_solicitud_assignment_service.py`).
> La **capa de datos, métricas y seguridad server-side de la Parte B** está implementada
> (ver §11) y la **interfaz productiva** (template, CSS, navegación, filtros reales del
> listado y pruebas) también (ver §12). Ninguna porción ha sido diferida a una tarea
> posterior. Quedan pendientes únicamente los criterios de verificación humana: el smoke
> en DEV (AC-9, AC-18) y las dos aprobaciones humanas independientes (AC-5, AC-7).

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
| REQ-A-04 | Transacción atómica | `UPDATE estado_lead` + `INSERT auditoria` commit atómico | AC-1 | Mismo `BEGIN/COMMIT` en `solicitud_repository.py`; sin commits intermedios | `tests/integration/test_lead_state_history.py::test_effective_change_records_actor_timestamp_states_and_single_event` | — (cubierto por test) | `developer-01.json` |
| REQ-A-05 | `SELECT ... FOR UPDATE` | Bloquear la fila del lead contra escrituras concurrentes | AC-1 | `SELECT ... FROM tpi.leads WHERE id_lead=%s FOR UPDATE` al inicio de `update_lead_status` | `tests/integration/test_lead_state_history.py::test_concurrent_updates_serialize_without_lost_update_or_duplicate_events` | — (cubierto por test) | `developer-01.json` |
| REQ-A-06 | No-op sin evento duplicado | Sin cambio real → sin evento de auditoría | AC-1 | Comparar `estado_anterior == estado_nuevo` → retornar sin escribir | `tests/integration/test_lead_state_history.py::test_noop_does_not_update_nor_duplicate_audit` | — (cubierto por test) | `developer-01.json` |
| REQ-A-07 | Rollback ante fallo de auditoría | Si falla el INSERT de auditoría, se revierte el estado | AC-1 | `ROLLBACK` completo si el INSERT falla; excepción propagada; `estado_lead` intacto | `tests/integration/test_lead_state_history.py::test_audit_failure_rolls_back_state` | — (cubierto por test) | `developer-01.json` |
| REQ-A-08 | Concurrencia real | Sin carreras ni eventos duplicados con dos conexiones | AC-1 | Test de integración con dos conexiones concurrentes sobre el mismo lead | `tests/integration/test_lead_state_history.py::test_concurrent_updates_serialize_without_lost_update_or_duplicate_events` | — (cubierto por test) | `developer-01.json` |
| REQ-A-09 | Acción de auditoría `cambio_estado_lead` | Contrato de la acción de auditoría | AC-2, AC-3 | Valor de `accion` escrito por la app y consumido por la vista 008 | `tests/unit/test_h3_3_4_migration_scripts.py` | — (cubierto por test) | `developer-01.json`; `migration-01.json` |
| REQ-A-10 | Migración 008 | Forward/rollback versionados del read model de estados | AC-2, AC-5, AC-6, AC-8 | `scripts/sql/008_create_lead_state_history.sql` + `scripts/sql/008_drop_lead_state_history.sql`; bootstrap en `scripts/init_test_database.py` | `tests/unit/test_h3_3_4_migration_scripts.py` (rollback probado en PostgreSQL local/integración) | Aprobación humana del migration candidate (AC-5) + postflight (AC-6) | `developer-01.json`; `migration-01.json` |
| REQ-A-11 | Vista sanitizada | `tpi.v_historial_estado_lead` sin datos sensibles ni JSON crudo | AC-3 | Vista `security_barrier` con columnas `id_auditoria, id_lead, fecha_hora, actor_subject, estado_anterior, estado_nuevo`; filtro `accion='cambio_estado_lead' AND tabla_afectada='tpi.leads'` | `tests/integration/test_audit_state_view.py::test_view_exposes_only_state_change_columns_and_filters_events` | — (cubierto por test) | `developer-01.json` |
| REQ-A-12 | Índices y EXPLAIN | Índices de apoyo justificados por plan real | AC-3 | Índice `auditoria_state_history_idx (accion, tabla_afectada, id_lead, fecha_hora)` justificado por EXPLAIN (aplicabilidad forzada con `enable_seqscan=off`; el `EXPLAIN ANALYZE` real sin forzar a volumen representativo queda como follow-up F2, ver §11.6); documentado en `docs/database/04_MIGRATIONS.md` | `tests/integration/test_audit_state_view.py::test_support_index_exists_and_is_used_for_state_history_query` | — (cubierto por test) | `developer-01.json` |
| REQ-A-13 | Mínimo privilegio | Solo `tpi_app` con SELECT sobre la vista; sin ampliar `tpi.auditoria` | AC-3, AC-6 | `REVOKE ALL ... FROM PUBLIC; GRANT SELECT ... TO tpi_app`; `tpi_app` sigue sin SELECT/UPDATE/DELETE sobre `tpi.auditoria` | `tests/integration/test_audit_state_view.py::test_view_privileges_public_and_app_only` | Postflight humano (AC-6) | `developer-01.json`; `migration-01.json.postflight` |
| REQ-A-14 | PUBLIC sin permisos | PUBLIC sin ningún privilegio sobre la vista | AC-3, AC-6 | `REVOKE ALL ON tpi.v_historial_estado_lead FROM PUBLIC` (preflight/postflight) | `tests/integration/test_audit_state_view.py::test_view_privileges_public_and_app_only` | Postflight humano (AC-6) | `migration-01.json.postflight` |
| REQ-A-15 | App sin SELECT directo a `tpi.auditoria` | El read model pasa solo por la vista | AC-3 | Repository lee `tpi.v_historial_estado_lead`; ningún `SELECT ... FROM tpi.auditoria` en `app/` | `tests/integration/test_audit_state_view.py::test_application_never_selects_auditoria_directly` | — (cubierto por test) | `developer-01.json` |
| REQ-A-16 | Timeline que combina notas, asignaciones 007 y cambios 008 | Una única línea de tiempo unificada | AC-4, AC-9 | `app/web/presentation.py::build_timeline_items` fusiona notas humanas + eventos 007 + eventos 008 | `tests/unit/test_h3_3_4_timeline_presentation.py`; regresión `tests/unit/test_h3_3_3_timeline_presentation.py` | Smoke autenticado (AC-9) | `developer-01.json`; `acceptance-01.json` |
| REQ-A-17 | Orden estable | Orden determinista cronológico | AC-4 | `fecha_hora DESC` + desempate determinístico por rango de fuente (`event` < `state_change` < `note`) y orden del repositorio | `tests/unit/test_h3_3_4_timeline_presentation.py::test_deterministic_tiebreak_event_then_state_change_then_note` | — (cubierto por test) | `developer-01.json` |
| REQ-A-18 | Badge "Automático" | Distinguir eventos de sistema | AC-4 | Badge "Automatico" para eventos de asignación y cambio de estado | `tests/unit/test_web_app.py::test_detail_timeline_renders_state_change_with_badge_and_no_edit_delete` | Smoke autenticado (AC-9) | `developer-01.json`; `acceptance-01.json` |
| REQ-A-19 | Eventos sin edición/eliminación | Timeline de solo lectura | AC-4 | Sin controles de editar/eliminar para eventos de sistema | `tests/unit/test_h3_3_4_timeline_presentation.py::test_state_change_items_have_no_edit_or_delete_controls`; `tests/unit/test_web_app.py` | Smoke autenticado (AC-9) | `developer-01.json`; `acceptance-01.json` |
| REQ-A-20 | No regresión de H3.3.3 | Comportamiento H3.3.3 intacto | AC-4, AC-9 | Regresión completa de tests H3.3.3 (timeline asignación, "Volver al sitio", notas) | `tests/unit/test_h3_3_3_timeline_presentation.py`; `tests/unit/test_backoffice_public_site_link.py`; `tests/unit/test_web_app.py` | Smoke autenticado (AC-9) | `developer-01.json`; `verification-01.json` |
| REQ-A-21 | No modificar 005/006/007 | Integridad de migraciones previas | AC-2 | La 008 no toca el contenido de 005/006/007; verificación de integridad | `tests/unit/test_h3_3_4_migration_scripts.py::test_008_does_not_modify_or_execute_005_006_007` | — (cubierto por test) | `developer-01.json` |
| REQ-A-22 | Ausencia de backfill inventado | Sin eventos retroactivos | AC-4 | No se generan eventos de estado anteriores al cutover 008; la cobertura se comunica sin fecha inventada | `tests/unit/test_h3_3_4_timeline_presentation.py::test_cutover_notice_never_invents_a_date_when_unconfigured` | — (cubierto por test) | `developer-01.json` |
| REQ-A-23 | Cobertura completa solo desde el cutover | Alcance temporal honesto | AC-4 | Aviso reproducible `LEAD_STATE_HISTORY_CUTOVER` (Settings) + `state_history_cutover_notice`; solo eventos reales posteriores al cutover 008 aparecen como cambios de estado | `tests/unit/test_h3_3_4_timeline_presentation.py::test_cutover_notice_uses_configured_date` | — (cubierto por test) | `developer-01.json` |
| REQ-A-24 | Conservación de asignaciones históricas recuperables | Asignaciones 007 previas siguen visibles | AC-4 | Los eventos de asignación 007 anteriores al cutover siguen proyectándose | `tests/unit/test_h3_3_4_timeline_presentation.py::test_backward_compatible_with_two_argument_callers`; regresión 007 | Smoke autenticado (AC-9) | `developer-01.json`; `acceptance-01.json` |

---

## 4. Parte B — Dashboard Ejecutivo (requisitos)

| REQ | Solicitud original | Objetivo | AC | Implementación prevista | Prueba automatizada | Smoke humano | Evidencia esperada |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-B-01 | Navegación "Dashboard Ejecutivo" | Entrada de menú dedicada | AC-10 | Enlace en `app/web/templates/base.html` (solo visible a ceo/cto) + `app/web/routes/dashboard.py` | `tests/unit/test_executive_dashboard_render.py::test_nav_link_is_visible_for_ceo`, `::test_nav_link_is_visible_for_cto`, `::test_nav_link_is_hidden_for_other_roles` | Sí (AC-18) | `developer-01.json` |
| REQ-B-02 | Acceso server-side exclusivo CEO/CTO | RBAC en servidor, no solo UI | AC-10 | Dependencia server-side (`require_executive_access` → `is_superuser(role)`) en el router del dashboard | `tests/unit/test_executive_dashboard_access.py::test_ceo_can_access_dashboard`, `::test_cto_can_access_dashboard`; `tests/unit/test_executive_dashboard_service.py::test_can_access_only_ceo_and_cto`; `tests/unit/test_executive_dashboard_render.py::test_hiding_the_link_is_not_the_access_control` | Sí (AC-18) | `developer-01.json` |
| REQ-B-03 | 403 real para cualquier otro rol y usuario no autenticado | Denegación real, sin datos | AC-10, AC-18 | `HTTPException(403)` para roles no ceo/cto y para no autenticado (sin render parcial, sin JSON) | `tests/unit/test_executive_dashboard_access.py::test_other_authenticated_role_receives_403`, `::test_anonymous_receives_403`; `tests/unit/test_executive_dashboard_render.py::test_rejected_response_carries_no_dashboard_structure_or_data`, `::test_anonymous_receives_403_without_dashboard_markup` | Smoke autenticado 403 (AC-18) | `developer-01.json`; `acceptance-01.json` |
| REQ-B-04 | Ausencia de filtraciones en HTML, API, JavaScript y source | Nada de datos del dashboard se sirve a roles no autorizados | AC-10 | El HTML/JS/source servido no embebe consultas ni datos del dashboard; el JSON solo se sirve en el endpoint autorizado | `tests/unit/test_executive_dashboard_access.py::test_no_dashboard_query_runs_on_rejection`, `::test_dashboard_route_does_not_leak_pii_in_rendered_placeholder`; `tests/unit/test_executive_dashboard_render.py::test_rejected_response_carries_no_dashboard_structure_or_data` | — (cubierto por test) | `developer-01.json` |
| REQ-B-05 | Total de leads | KPI cardinal | AC-11 | `COUNT(DISTINCT id_lead)` sobre `tpi.leads` | `tests/integration/test_executive_dashboard_repository.py::test_single_lead_metrics`, `::test_zero_data_returns_empty_metrics` | Sí (AC-18) | `developer-01.json` |
| REQ-B-06 | Leads ingresados durante el período (fecha_ingreso) | KPI con fuente temporal correcta | AC-11 | Usa `fecha_ingreso` (no `created_at`), con la diferencia documentada | `tests/integration/test_executive_dashboard_repository.py::test_inclusive_date_boundaries`, `::test_evolucion_granularity_and_santiago_timezone` | Sí (AC-18) | `developer-01.json` |
| REQ-B-07 | Casos por estado | Desglose por estado | AC-11 | Agregación `COUNT(DISTINCT id_lead) GROUP BY estado_lead` | `tests/integration/test_executive_dashboard_repository.py::test_unknown_states_are_preserved`; `tests/unit/test_executive_dashboard_service.py::test_unknown_states_are_preserved_with_safe_label` | Sí (AC-18) | `developer-01.json` |
| REQ-B-08 | Asignados y sin asignar | Conteo con/sin asignación activa | AC-11 | LEFT JOIN `tpi.asignaciones` (activa) con `COUNT(DISTINCT id_lead)` | `tests/integration/test_executive_dashboard_repository.py::test_leads_sin_asesor_have_own_bucket`, `::test_inactive_assignments_do_not_count_and_fanout_is_safe` | Sí (AC-18) | `developer-01.json` |
| REQ-B-09 | Evolución diaria, semanal y mensual | Serie temporal | AC-11 | Bucketing por día/semana/mes sobre `fecha_ingreso` (y transiciones) | `tests/integration/test_executive_dashboard_repository.py::test_evolucion_granularity_and_santiago_timezone`; `tests/unit/test_executive_dashboard_presentation.py::test_bucket_labels_follow_the_selected_granularity` | Sí (AC-18) | `developer-01.json` |
| REQ-B-10 | Filtros individuales y combinados | Filtros componibles | AC-11, AC-18 | Filtros por período + estado + asesor + AFP + origen + fuente, combinables | `tests/unit/test_executive_dashboard_filters.py`; `tests/integration/test_executive_dashboard_repository.py::test_individual_and_combined_filters` | Sí (AC-18) | `developer-01.json` |
| REQ-B-11 | Distribución por estado | Breakdown por categoría MVP "estado" | AC-16 | `GROUP BY estado_lead` (solo categorías MVP) | `tests/integration/test_executive_dashboard_repository.py::test_unknown_states_are_preserved`; `tests/unit/test_executive_dashboard_presentation.py::test_unknown_state_keeps_its_raw_value_as_label` | Sí (AC-18) | `developer-01.json` |
| REQ-B-12 | Resumen por asesor | Agregación por asesor | AC-12 | `GROUP BY asesor` (JOIN `tpi.asesores` para nombre) | `tests/integration/test_executive_dashboard_full.py::test_per_advisor_metrics_use_the_shared_definitions` | Sí (AC-18) | `developer-01.json` |
| REQ-B-13 | Cartera total y activa por asesor | Distinción cartera total vs activa | AC-12 | Cartera activa = `estado_lead NOT IN (cerrado, perdido, no_califica, duplicado)` | `tests/integration/test_executive_dashboard_repository.py::test_cartera_activa_excludes_closed_states`; `tests/integration/test_executive_dashboard_full.py::test_per_advisor_metrics_use_the_shared_definitions` | Sí (AC-18) | `developer-01.json` |
| REQ-B-14 | Casos por estado y asesor | Matriz estado × asesor | AC-12 | `GROUP BY asesor, estado_lead` con `COUNT(DISTINCT id_lead)` | `tests/integration/test_executive_dashboard_full.py::test_per_advisor_metrics_use_the_shared_definitions`; `tests/unit/test_executive_dashboard_render.py::test_state_by_advisor_matrix_is_available_without_extra_columns` | Sí (AC-18) | `developer-01.json` |
| REQ-B-15 | Casos estancados | Detección de estancamiento operacional | AC-13 | Estancado = 5 días corridos sin movimiento operativo (nota/asignación/cambio de estado, nunca solo `updated_at`); umbral configurable default=5 | `tests/integration/test_executive_dashboard_repository.py::test_estancamiento_counts_only_no_recent_movement` | Sí (AC-18) | `developer-01.json` |
| REQ-B-16 | Antigüedad | Buckets de días corridos | AC-13 | Buckets 0-2, 3-7, 8-15, 16-30, +30 días corridos (no hábiles) | `tests/integration/test_executive_dashboard_repository.py::test_antiguedad_buckets`; `tests/unit/test_executive_dashboard_presentation.py::test_age_ladder_returns_the_five_approved_buckets_in_order` | Sí (AC-18) | `developer-01.json` |
| REQ-B-17 | Tiempo hasta asignación | Métrica de asignación | AC-14 | Diferencia `fecha_ingreso → primera asignación` | `tests/integration/test_executive_dashboard_repository.py::test_tiempo_asignacion_media` | Sí (AC-18) | `developer-01.json` |
| REQ-B-18 | Tiempo hasta primera gestión | Primera gestión operacional | AC-14 | Primera gestión = primera nota humana o primer cambio general de estado (excluye asignación automática); NULL/N/D si no existe | `tests/integration/test_executive_dashboard_repository.py::test_tiempo_primera_gestion_excludes_assignment`; `tests/integration/test_executive_dashboard_full.py::test_first_management_is_unavailable_without_a_cutover` | Sí (AC-18) | `developer-01.json` |
| REQ-B-19 | Funnel y tasas observables | Tasas honestas | AC-15 | Solo transiciones observables; pre-cutover sin historia completa no generan tasas; `COUNT(DISTINCT id_lead)` | `tests/integration/test_executive_dashboard_repository.py::test_funnel_excludes_pre_cutover_leads`, `::test_funnel_missing_cutover_yields_no_rates`, `::test_funnel_period_fully_after_cutover_computes_rates`, `::test_funnel_zero_denominator_yields_no_transitions`, `::test_funnel_preserves_unknown_states`, `::test_funnel_repeated_transition_is_counted_once`, `::test_funnel_return_to_previous_state_keeps_both_transitions`; `tests/unit/test_executive_dashboard_presentation.py::test_funnel_is_available_with_complete_coverage`, `::test_funnel_is_withheld_without_cutover`, `::test_funnel_is_withheld_without_a_period`, `::test_funnel_is_withheld_when_coverage_is_partial`, `::test_funnel_is_withheld_without_observable_transitions` | Sí (AC-18) | `developer-01.json` |
| REQ-B-20 | Tarjetas KPI | UI de tarjetas | AC-11 | `app/web/templates/executive_dashboard.html` + presenter | `tests/unit/test_executive_dashboard_render.py::test_kpi_cards_render_every_headline_metric`; `tests/unit/test_executive_dashboard_service.py::test_snapshot_kpis_are_mapped` | Sí (AC-18) | `developer-01.json` |
| REQ-B-21 | Serie temporal | Gráfico de evolución | AC-11 | Render de serie temporal (presenter/template) | `tests/unit/test_executive_dashboard_presentation.py::test_timeseries_is_none_without_observations`, `::test_timeseries_with_a_single_observation_has_no_polyline`, `::test_timeseries_with_all_zero_values_stays_on_the_baseline`, `::test_timeseries_never_fabricates_points`; `tests/unit/test_executive_dashboard_render.py::test_timeseries_with_a_single_point_renders_a_marker_and_no_polyline` | Sí (AC-18) | `developer-01.json` |
| REQ-B-22 | Categorías MVP | Restricción de dimensiones | AC-16 | Solo estado, asesor, AFP, origen del lead, fuente actual | `tests/unit/test_executive_dashboard_service.py::test_contract_uses_only_mvp_categories`; `tests/unit/test_executive_dashboard_render.py::test_mvp_categories_only_no_gender_or_marital_status`; `tests/integration/test_executive_dashboard_full.py::test_filter_options_expose_only_mvp_categories_without_pii` | — (cubierto por test) | `developer-01.json` |
| REQ-B-23 | Estados vacíos y de error | UX coherente sin datos/error | AC-17 | Estados vacíos y de error en template | `tests/unit/test_executive_dashboard_render.py::test_dashboard_without_data_shows_coherent_empty_states`, `::test_partial_failure_reports_the_section_and_keeps_the_rest`, `::test_failed_section_never_renders_as_zero`, `::test_global_error_returns_a_safe_page_without_internal_details` | Sí (AC-18) | `developer-01.json` |
| REQ-B-24 | Interfaz responsive | Usabilidad multi-dispositivo | AC-17 | CSS responsive (`app/web/static/css/`) | `tests/unit/test_executive_dashboard_render.py::test_charts_are_server_rendered_without_javascript_or_cdn`, `::test_every_chart_has_a_title_a_summary_and_an_accessible_table`, `::test_page_has_no_required_javascript_for_filtering` (contrato de UX server-rendered); responsive validado por auditoría visual (§12.9) + smoke humano | Sí (AC-18) | `developer-01.json`; `acceptance-01.json` |
| REQ-B-25 | Coherencia con la Web UX actual | Consistencia visual/estructural | AC-17 | Mismos patrones Jinja/CSS del backoffice actual | `tests/unit/test_executive_dashboard_render.py::test_normal_render_shows_both_scopes_explicitly`, `::test_filters_are_a_get_form_with_labelled_controls` (patrones Jinja/CSS del backoffice); revisión visual humana | Sí (AC-18) | `developer-01.json` |
| REQ-B-26 | Ausencia de BI externo | Sin dependencia de BI | AC-17 | Sin integración de plataforma BI externa | `tests/unit/test_executive_dashboard_render.py::test_charts_are_server_rendered_without_javascript_or_cdn`, `::test_no_aggregate_data_is_embedded_in_scripts_or_comments` | — (cubierto por test) | `developer-01.json` |
| REQ-B-27 | Cero PII de leads | Sin PII de leads | AC-17 | Sin RUT, nombres, teléfono, correo ni otra PII; métricas agregadas | `tests/unit/test_executive_dashboard_render.py::test_served_html_contains_no_pii_value_of_any_kind`; `tests/unit/test_executive_dashboard_service.py::test_contract_contains_no_lead_or_advisor_pii`; `tests/integration/test_executive_dashboard_full.py::test_advisor_rows_expose_no_pii_beyond_the_visible_name` | — (cubierto por test) | `developer-01.json` |
| REQ-B-28 | Nombre del asesor visible solo para CEO/CTO | PII de asesor acotada | AC-12 | Nombre del asesor visible solo en el endpoint ceo/cto; nunca RUT/teléfono/correo | `tests/unit/test_executive_dashboard_render.py::test_advisor_table_shows_only_the_allowed_columns`; `tests/integration/test_executive_dashboard_full.py::test_advisor_rows_expose_no_pii_beyond_the_visible_name` | — (cubierto por test) | `developer-01.json` |
| REQ-B-29 | Pruebas de rendimiento | Validación de volumen | AC-18 | Test con volumen representativo + `EXPLAIN` documentado | `tests/integration/test_executive_dashboard_full.py::test_full_dashboard_latency_with_representative_volume`, `::test_full_dashboard_query_count_is_bounded_and_free_of_n_plus_1`; `tests/integration/test_executive_dashboard_repository.py::test_performance_representative_volume`, `::test_explain_state_history_uses_support_index`; benchmark reproducible `scripts/benchmark_executive_dashboard.py` | — (cubierto por test) | `developer-01.json` |
| REQ-B-30 | Smoke completo en AWS DEV | Verificación real Parte B | AC-18 | Smoke humano en DEV: acceso ceo/cto, 403 roles no autorizados, KPIs y filtros | — (smoke humano) | Smoke humano completo (AC-18) | `acceptance-01.json`; `verification-01.json` |

---

## 5. Seguridad, migración y operación (requisitos)

| REQ | Solicitud original | Objetivo | AC | Implementación prevista | Prueba automatizada | Smoke humano | Evidencia esperada |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-S-01 | change_class D | Clasificación correcta del cambio | AC-5, AC-7 | `tasks/current.yaml.change_class=D`; la migración 008 fuera del fast path | — (verificación de guards: `deploy_required_non_fast_path`) | Human Gate (BLOCKED_HUMAN) | `merge-01.json` (merged_non_fast_path) |
| REQ-S-02 | 008 debe reconfirmarse libre antes de desarrollarla | Número de migración correcto | AC-2 | Verificar `008` libre en todo el historial git antes de escribir el forward/rollback | `tests/unit/test_h3_3_4_migration_scripts.py` (verificación de numeración) | — (cubierto por verificación) | `developer-01.json` |
| REQ-S-03 | Migration candidate y application candidate separados | Dos artefactos distintos | AC-5, AC-7 | Congelar migration candidate (SHA main + forward/rollback con SHA-256) y, aparte, application candidate | — (verificación humana del artefacto; SHA-256 por script de preflight) | Dos aprobaciones humanas | `migration-01.json`; `candidate-01.json` |
| REQ-S-04 | Dos aprobaciones humanas independientes y no intercambiables | Ninguna aprobación sustituye a la otra | AC-5, AC-7 | Aprobación migration candidate ≠ aprobación application candidate (WAITING_HUMAN_APPROVAL) | — (verificación humana; no sustituible por test) | Dos Human Gates | `resolution-01.json` (migration) + `approval-01.json` (application) |
| REQ-S-05 | Postflight DB antes de application candidate | Orden de etapas | AC-6, AC-7 | Postflight de privilegios (AC-6) PASS antes de resolver a PREPARING_DEPLOYMENT | — (verificación humana del postflight) | Postflight humano (AC-6) | `migration-01.json.postflight` |
| REQ-S-06 | Ningún fast path | Migración nunca por fast path | AC-5 | `merged_non_fast_path → BLOCKED_HUMAN` obligatorio (clase D) | — (verificación de guards) | Human Gate | `merge-01.json` |
| REQ-S-07 | Sin option-settings | Sin mutación de settings | AC-7 | Plan de deploy sin `--option-settings` | `tests/security/test_eb_deployment_security.py` (regresión, sin option-settings) | — (cubierto por guard) | `candidate-01.json` (deployment_plan) |
| REQ-S-08 | Rollback probado en integración | Rollback 008 validado antes de DEV | AC-8 | `008_drop_lead_state_history.sql` (REVOKE + DROP VIEW) probado en PostgreSQL de integración | `tests/unit/test_h3_3_4_migration_scripts.py::test_rollback_revokes_select_and_drops_view_and_index` | — (cubierto por test) | `developer-01.json` |
| REQ-S-09 | Fallos sin eliminación automática de evidencia u objetos | Sin borrado automático | AC-8 | Ningún fallo post-deploy elimina automáticamente evidencia ni objetos | `tests/unit/test_h3_3_4_migration_scripts.py::test_forward_and_rollback_are_separate_transactional_scripts`, `::test_rollback_revokes_select_and_drops_view_and_index` (borrado controlado, nunca automático) | — (cubierto por test) | `developer-01.json` |
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
| TC-1 | Cambio de estado registra actor/fecha/anterior/nuevo | REQ-A-01, REQ-A-02 | AC-1 | `tests/integration/test_lead_state_history.py::test_effective_change_records_actor_timestamp_states_and_single_event` | `developer-01.json` |
| TC-2 | No-op sin duplicación | REQ-A-06 | AC-1 | `tests/integration/test_lead_state_history.py::test_noop_does_not_update_nor_duplicate_audit` | `developer-01.json` |
| TC-3 | Concurrencia con dos conexiones | REQ-A-08 | AC-1 | `tests/integration/test_lead_state_history.py::test_concurrent_updates_serialize_without_lost_update_or_duplicate_events` | `developer-01.json` |
| TC-4 | Fallo de auditoría revierte el estado | REQ-A-07 | AC-1 | `tests/integration/test_lead_state_history.py::test_audit_failure_rolls_back_state` | `developer-01.json` |
| TC-5 | Timeline combina las tres fuentes | REQ-A-16 | AC-4 | `tests/unit/test_h3_3_4_timeline_presentation.py::test_merges_three_sources_chronologically` | `developer-01.json` |
| TC-6 | Orden estable y America/Santiago | REQ-A-03, REQ-A-17 | AC-4 | `tests/unit/test_h3_3_4_timeline_presentation.py::test_state_change_timestamp_is_displayed_in_america_santiago`, `::test_deterministic_tiebreak_event_then_state_change_then_note` | `developer-01.json` |
| TC-7 | Eventos automáticos no editables | REQ-A-18, REQ-A-19 | AC-4 | `tests/unit/test_web_app.py::test_detail_timeline_renders_state_change_with_badge_and_no_edit_delete`; `tests/unit/test_h3_3_4_timeline_presentation.py::test_state_change_items_have_no_edit_or_delete_controls` | `developer-01.json` |
| TC-8 | CEO y CTO acceden | REQ-B-02 | AC-10 | `tests/unit/test_executive_dashboard_access.py::test_ceo_can_access_dashboard`, `::test_cto_can_access_dashboard` | `developer-01.json` |
| TC-9 | Otros roles y anónimos reciben 403 sin datos | REQ-B-03 | AC-10 | `tests/unit/test_executive_dashboard_access.py::test_other_authenticated_role_receives_403`, `::test_anonymous_receives_403` | `developer-01.json` |
| TC-10 | KPIs con cero datos | REQ-B-05, REQ-B-20 | AC-11, AC-18 | `tests/integration/test_executive_dashboard_repository.py::test_zero_data_returns_empty_metrics`; `tests/unit/test_executive_dashboard_render.py::test_dashboard_without_data_shows_coherent_empty_states` | `developer-01.json` |
| TC-11 | Filtros individuales y combinados | REQ-B-10 | AC-11 | `tests/unit/test_executive_dashboard_filters.py`; `tests/integration/test_executive_dashboard_repository.py::test_individual_and_combined_filters` | `developer-01.json` |
| TC-12 | Límites de fecha | REQ-B-06 | AC-11 | `tests/integration/test_executive_dashboard_repository.py::test_inclusive_date_boundaries` | `developer-01.json` |
| TC-13 | Evolución diaria/semanal/mensual | REQ-B-09 | AC-11 | `tests/integration/test_executive_dashboard_repository.py::test_evolucion_granularity_and_santiago_timezone`; `tests/unit/test_executive_dashboard_presentation.py::test_bucket_labels_follow_the_selected_granularity` | `developer-01.json` |
| TC-14 | Leads sin asesor | REQ-B-08 | AC-11, AC-18 | `tests/integration/test_executive_dashboard_repository.py::test_leads_sin_asesor_have_own_bucket` | `developer-01.json` |
| TC-15 | Estados desconocidos o históricos | REQ-B-07 | AC-11, AC-18 | `tests/integration/test_executive_dashboard_repository.py::test_unknown_states_are_preserved` | `developer-01.json` |
| TC-16 | Fan-out de joins sin conteos duplicados | REQ-B-07, REQ-B-14 | AC-11, AC-12, AC-18 | `tests/integration/test_executive_dashboard_repository.py::test_inactive_assignments_do_not_count_and_fanout_is_safe` | `developer-01.json` |
| TC-17 | Resumen por asesor | REQ-B-12 | AC-12 | `tests/integration/test_executive_dashboard_full.py::test_per_advisor_metrics_use_the_shared_definitions` | `developer-01.json` |
| TC-18 | PII no expuesta | REQ-B-27 | AC-17 | `tests/unit/test_executive_dashboard_render.py::test_served_html_contains_no_pii_value_of_any_kind`; `tests/unit/test_executive_dashboard_service.py::test_contract_contains_no_lead_or_advisor_pii` | `developer-01.json` |
| TC-19 | Rendimiento con volumen representativo y EXPLAIN | REQ-A-12, REQ-B-29 | AC-3, AC-18 | `tests/integration/test_executive_dashboard_full.py::test_full_dashboard_latency_with_representative_volume`, `::test_full_dashboard_query_count_is_bounded_and_free_of_n_plus_1`; `tests/integration/test_executive_dashboard_repository.py::test_performance_representative_volume`, `::test_explain_state_history_uses_support_index` | `developer-01.json` |
| TC-20 | Regresión H3.3/H3.3.3 | REQ-A-20 | AC-4, AC-9 | `tests/unit/test_h3_3_3_timeline_presentation.py`; `tests/unit/test_web_app.py` | `developer-01.json`; `verification-01.json` |
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

> Desde la ronda 1 de revisión, este gate está **automatizado y ampliado** en
> `tests/unit/test_h3_3_4_requirements_matrix_gate.py`, que además verifica que toda ruta
> de prueba citada existe, que todo `::test_<nombre>` resuelve a una función real, que no
> aparece ninguna referencia a una tarea posterior, que AC-1..AC-18 siguen cubiertos, que
> los requirement IDs son únicos y completos, y que ninguna fila de requisito queda sin AC
> ni apuntando a un archivo inexistente.

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

---

## 10. Diseño de Parte B (sesión de diseño y prototipado)

> Sesión posterior, exclusiva de diseño (skill `anthropic-skills:frontend-design`),
> sin código productivo. No cambia el estado "pendiente de implementación" de la
> Parte B registrado en §0 y §9; solo documenta el diseño aprobado como insumo
> para la implementación futura.

- **Diseño**: `docs/H3_3_4_DASHBOARD_DESIGN.md` (propuestas A/B/C, arquitectura
  visual de 12 elementos, decisión técnica de gráficos, tokens/accesibilidad/
  responsive, revisión visual).
- **Prototipo**: `docs/prototypes/H3_3_4_dashboard_prototype.html` (HTML
  autocontenido, datos sintéticos, sin red, sin CDN, sin autenticación, con
  controles de demostración para los estados normal/cero datos/error
  parcial/cobertura histórica limitada). No está conectado a ninguna ruta de
  la aplicación.
- **Alternativa recomendada**: C — híbrida (resumen ejecutivo arriba, análisis
  progresivo al centro, detalle operacional abajo), justificada en
  `docs/H3_3_4_DASHBOARD_DESIGN.md` §4.
- **Decisión técnica de gráficos**: HTML/CSS + SVG server-rendered (sin
  librería JS, sin CDN); ver `docs/H3_3_4_DASHBOARD_DESIGN.md` §7.

### Mapeo secciones de diseño ↔ REQ-B ↔ AC

| Sección del diseño (Fase 2) | REQ-B relacionados | AC |
| --- | --- | --- |
| 1. Encabezado y navegación | REQ-B-01, REQ-B-02, REQ-B-03, REQ-B-04 | AC-10 |
| 2. Barra de filtros | REQ-B-10 | AC-11, AC-18 |
| 3. Primera fila de KPIs | REQ-B-05, REQ-B-06, REQ-B-07, REQ-B-08, REQ-B-20 | AC-11 |
| 4. Alertas operacionales | REQ-B-08, REQ-B-15 | AC-11, AC-13 |
| 5. Distribución por estado | REQ-B-07, REQ-B-11, REQ-B-22 | AC-11, AC-16 |
| 6. Evolución temporal | REQ-B-09, REQ-B-21 | AC-11 |
| 7. Antigüedad | REQ-B-15, REQ-B-16 | AC-13 |
| 8. Distribución por categorías | REQ-B-11, REQ-B-22 | AC-16 |
| 9. Funnel | REQ-B-19 | AC-15 |
| 10. Resumen por asesor | REQ-B-12, REQ-B-13, REQ-B-14, REQ-B-17, REQ-B-18, REQ-B-28 | AC-12, AC-14 |
| 11. Aviso de cobertura | REQ-B-19 | AC-15 |
| 12. Estados vacíos y de error | REQ-B-23 | AC-17 |
| Sistema visual, tokens, accesibilidad, responsive (§8-§10 del diseño) | REQ-B-24, REQ-B-25, REQ-B-26, REQ-B-27 | AC-17 |

### Decisiones visuales registradas

- Reutilización íntegra de los tokens de `app/web/static/css/app.css`
  (colores, radios, sombra, tipografía) y de los componentes existentes
  (`.card`, `.filters-grid`, `.table-wrap`/`.board-table`, `.empty-state`,
  `.notice-soft`/`.alert-error`); ninguno se reemplaza.
- Clases nuevas especificadas (no creadas en `app.css` en esta sesión):
  `.kpi-grid`/`.kpi-card`, `.alert-chip`, `.bar-list`/`.bar-row`/`.bar-track`/
  `.bar-fill`, `.age-ladder`/`.age-step` (elemento distintivo: antigüedad como
  "escalera" con intensidad de borde creciente, siempre acompañada de texto),
  `.timeseries*`, `.funnel-list`/`.funnel-row`, `.coverage-banner`.
- Género y estado civil no aparecen en ninguna sección del diseño ni del
  prototipo, ni como dimensión activa ni como trabajo futuro.
- Nombre del asesor visible en el diseño; RUT, teléfono y correo del asesor
  nunca aparecen en ninguna sección.

### Componentes futuros de implementación (fuera de alcance de esta sesión)

Ver `docs/H3_3_4_DASHBOARD_DESIGN.md` §13 para el detalle completo:
router `app/web/routes/dashboard.py` con control de acceso server-side,
capa de agregación en `SolicitudService`/`SolicitudRepository`, plantilla
`executive_dashboard.html` + parciales, extensión de `app.css` con las
clases especificadas en §8 del diseño, suite de pruebas por REQ-B y smoke
humano en AWS DEV (AC-18).

---

## 11. Parte B (capa de datos) — implementación real

> Sesión Developer (Parte B). Se implementa **exclusivamente** la capa de datos,
> métricas y seguridad server-side. La interfaz productiva (template visual
> definitivo y CSS) continúa pendiente dentro de H3.3.4. Sin PR, sin
> `submit_for_review`, sin AWS/RDS, sin aplicar migración en DEV.

### 11.1 Contrato temporal `current_snapshot` vs `period_activity`

El contrato de respuesta (`app/models/executive_dashboard.py::ExecutiveDashboard`)
identifica explícitamente el `scope` de cada métrica:

- **`current_snapshot`** (estado vigente al momento de la consulta): total histórico
  de leads, cartera activa, sin asignar, estancados, casos por estado, antigüedad,
  estancados por antigüedad, cartera por asesor, casos por estado y asesor, y
  distribución actual por AFP/origen/fuente. Los filtros de dimensión aplican; el
  rango temporal **no** restringe estas métricas (no se convierten en cohorte de
  ingresos).
- **`period_activity`** (usa `fecha_ingreso` dentro del rango): leads ingresados,
  evolución diaria/semanal/mensual, funnel observable, y métricas temporales
  (`tiempo_asignacion` y `tiempo_primera_gestion`, duraciones sobre la población
  definida por los filtros de dimensión; no cohortes por rango de fechas).

No se presenta ningún snapshot histórico "al cierre de una fecha pasada": no existe
historia completa para reconstruirlo y el contrato no lo fabrica.

### 11.2 Archivos

| Componente | Archivo |
| --- | --- |
| Contratos tipados + filtros validados | `app/models/executive_dashboard.py` |
| Repositorio agregado | `app/repositories/executive_dashboard_repository.py` |
| Servicio (orquestación + scope) | `app/services/executive_dashboard_service.py` |
| Autorización server-side + ruta mínima | `app/web/routes/dashboard.py` |
| Registro del router | `app/web/main.py` |
| Placeholder mínimo (no visual definitivo) | `app/web/templates/executive_dashboard.html` |

### 11.3 Consultas y métricas

Repositorio `ExecutiveDashboardRepository` (todos los conteos usan
`COUNT(DISTINCT id_lead)` cuando existe fan-out; todas las consultas
parametrizadas con `%s`; los fragmentos interpolados son constantes
whitelisted envueltas en `psycopg.sql.SQL`):

- `get_kpi_snapshot` — total, cartera activa (`estado_lead NOT IN (cerrado, perdido,
  no_califica, duplicado)`), sin asignar (sin asignación activa).
- `get_estancados` / `get_estancados_por_antiguedad` — último movimiento =
  `GREATEST(fecha_ingreso, MAX(asignación), MAX(cambio de estado), MAX(nota humana))`;
  estancado si `ultimo_movimiento <= now() - make_interval(days => umbral)` (default 5).
  `updated_at` nunca se usa; piso reproducible `fecha_ingreso` si no hay movimiento.
- `get_casos_por_estado` — `GROUP BY estado_lead` (estados desconocidos conservados).
- `get_antiguedad` — buckets 0-2/3-7/8-15/16-30/+30 días corridos (calendario) sobre
  la cartera activa, en `America/Santiago`.
- `get_cartera_por_asesor` / `get_casos_por_estado_y_asesor` — asignación activa
  (`DISTINCT ON`); leads sin asesor en bucket propio; solo `id_asesor` + `nombre`.
- `get_distribucion_afp/origen/fuente` — categorías MVP; valores desconocidos
  etiquetados de forma segura (`Sin AFP`/`Sin origen`/`Sin fuente`).
- `get_leads_ingresados` / `get_evolucion` — `fecha_ingreso` inclusivo en el rango;
  granularidad whitelist `diaria`/`semanal`/`mensual` (`date_trunc` en Santiago).
- `get_funnel` — solo transiciones observables de `v_historial_estado_lead` (008) para
  leads post-cutover; pre-cutover excluidos de tasas; cada paso lleva `n`/`base`/`rate`.
- `get_tiempo_asignacion` — media de días `fecha_ingreso → primera asignación`
  (operacional `tpi.asignaciones`).
- `get_tiempo_primera_gestion` — media de días `fecha_ingreso → primera nota humana o
  primer cambio general de estado` (excluye asignación); post-cutover; `NULL/N-D` si no
  existe.

La aplicación **nunca** consulta `tpi.auditoria` directamente: el historial de estados
se lee de `tpi.v_historial_estado_lead` (008) y el movimiento de asignación de la tabla
operacional `tpi.asignaciones` (mismo patrón de mínimo privilegio que la Parte A).

### 11.4 RBAC, PII y filtros

- **RBAC**: `require_executive_access` (ruta) y `ExecutiveDashboardService.can_access`
  solo admiten `ceo`/`cto` (`is_superuser`). Cualquier otro rol autenticado y el
  anónimo reciben **403 real** antes de ejecutar cualquier consulta (la consulta no se
  ejecuta tras el rechazo; cubierto por test con servicio espía).
- **PII de leads**: cero PII en el contrato (métricas agregadas únicamente).
- **PII de asesor**: solo `id_asesor` (identificador técnico) + `nombre` visible +
  métricas agregadas; nunca RUT/correo/teléfono del asesor.
- **Filtros** (`DashboardFilters.from_raw`): whitelist de granularidad, fechas ISO
  inclusivas con rechazo de rango inválido (`desde > hasta` → `ValueError`), UUID
  validados para asesor/AFP, texto normalizado para origen/fuente, valores desconocidos
  sin romper la consulta.

### 11.5 Enlaces "ver detalle" (contrato, no URLs decorativas)

El contrato `AlertTarget` expone `sin_asignar` y `estancados` con `filters`:
`{"sin_asignar": true}` y `{"estancado": true}`. El listado actual (`/leads`,
`app/web/routes/leads.py`) **no** soporta aún estos parámetros. Extensión exacta
necesaria para la sesión visual: (1) en `leads.py::_resolve_board_data` leer
`sin_asignar`/`estancado` de `query_params`; (2) en `SolicitudRepository`
`_build_crm_query_filters` aceptar `sin_asignar` (`NOT EXISTS` asignación activa) y
`estancado` (mismo cálculo de último movimiento que el dashboard); (3) propagar ambos
parámetros a la URL de la bandeja. No se agregan rutas ni enlaces inexistentes.

### 11.6 EXPLAIN y rendimiento

- `tests/integration/test_executive_dashboard_repository.py::test_explain_state_history_uses_support_index`
  ejecuta `EXPLAIN (FORMAT JSON)` sobre la agregación de `v_historial_estado_lead` y
  verifica que el índice de apoyo `auditoria_state_history_idx` (008) es **aplicable**:
  lo hace con `SET LOCAL enable_seqscan = off` para forzar el camino de índice, porque
  con la tabla de integración (pequeña) el planificador de PostgreSQL elige naturalmente
  el seq scan. **Esta prueba demuestra la aplicabilidad del índice, no el plan normal de
  PostgreSQL a volumen real.**
- `test_performance_representative_volume` siembra 1.500 leads y verifica que
  `get_kpi_snapshot` + `get_estancados` completan < 5 s con conteos correctos.
- Las cifras "~40x latencia / ~90x buffers a 100k filas" citadas en el comentario de
  `scripts/sql/008_create_lead_state_history.sql` y en `docs/database/04_MIGRATIONS.md`
  provienen de la comparación con el camino de índice **forzado** (`enable_seqscan=off`),
  no del plan elegido normalmente por PostgreSQL a ese volumen. El `EXPLAIN (ANALYZE,
  BUFFERS)` real sin forzar a volumen representativo queda como follow-up (F2 de
  `evidence/H3.3.4/reviewer/review-01.json`) a adjuntar antes del cierre de la tarea.
  `scripts/benchmark_executive_dashboard.py` ya ejecuta `EXPLAIN (ANALYZE, BUFFERS)` real
  sin forzar sobre los dos riesgos de escalado (parser regexp de notas y agregación de
  `v_historial_estado_lead`), pero no reproduce la comparación Seq-Scan-vs-Index-Scan a
  100k filas.
- **No se agregó ningún índice nuevo**: el índice 008 ya cubre la agregación de estado;
  no hay evidencia que justifique uno adicional.

### 11.7 Pruebas

- Unitarias: `tests/unit/test_executive_dashboard_filters.py` (filtros),
  `tests/unit/test_executive_dashboard_service.py` (contrato/PII/porcentajes/MVP),
  `tests/unit/test_executive_dashboard_access.py` (RBAC 403/200, sin consulta tras
  rechazo).
- Integración: `tests/integration/test_executive_dashboard_repository.py` (cero datos,
  un lead, sin asesor, asignaciones históricas/inactivas, estados desconocidos, filtros
  individuales/combinados, límites de fechas, America/Santiago, granularidad, fan-out,
  cartera activa, estancamiento, antigüedad, tiempo asignación/primera gestión, funnel
  pre/post-cutover, EXPLAIN y volumen).
- Suite completa: **601 passed, 3 failed** (los 3 `test_frozen_candidate_verification`
  pre-existentes con WSL `E_ACCESSDENIED`, causa ya demostrada; no modificados ni
  marcados skip/xfail). Cobertura **87%** (≥85).

### 11.8 Pendientes exactos para la interfaz (sesión visual)

1. Template productivo `executive_dashboard.html` + parciales por sección según
   `docs/H3_3_4_DASHBOARD_DESIGN.md` §5 (alternativa C) y clases de §8.
2. Extensión de `app/web/static/css/app.css` con las clases nuevas especificadas en
   `docs/H3_3_4_DASHBOARD_DESIGN.md` §8 (`.kpi-grid`, `.bar-list`, `.age-ladder`,
   `.timeseries*`, `.funnel-list`, `.coverage-banner`, `.alert-chip`), sin modificar
   las existentes.
3. Entrada de navegación "Dashboard Ejecutivo" en `base.html` (visible solo ceo/cto).
4. Soporte de filtros `sin_asignar`/`estancado` en el listado `/leads` (ver §11.5).
5. Smoke humano en DEV (AC-18), incluido el 403 real para roles no autorizados.

> **Estado de §11.8**: los puntos 1 a 4 quedaron implementados en la sesión de interfaz
> productiva (ver §12). El punto 5 sigue pendiente por ser verificación humana.

---

## 12. Parte B (interfaz productiva) — implementación real

> Sesión Developer (Parte B, interfaz). Convierte el prototipo aprobado
> (`docs/prototypes/H3_3_4_dashboard_prototype.html`, alternativa C del diseño) en la
> interfaz productiva, conectada exclusivamente a las métricas reales. Sin datos
> sintéticos en la aplicación, sin plataforma BI, sin CDN, sin framework frontend ni
> librería de gráficos. Sin PR, sin `submit_for_review`, sin acceso a AWS/RDS.

### 12.1 Preflight del contrato (ejecutado antes de construir la UI)

| Verificación | Resultado |
| --- | --- |
| `LEAD_STATE_HISTORY_CUTOVER` ausente ⇒ funnel no disponible | Confirmado: `get_funnel` devuelve `cobertura_completa=False` y la UI muestra "No disponible con cobertura suficiente" con la razón explícita |
| No se calculan tasas sin cobertura completa | `Funnel.disponible` exige cutover + período + `excluidos_pre_cutover == 0` + `denominador > 0` + transiciones observables |
| `SET enable_seqscan = off` en runtime | Ausente: única aparición en `tests/integration/test_executive_dashboard_repository.py` (prueba de `EXPLAIN`) |
| Latencia real medida con volumen representativo | Sí, medida end-to-end (ver §12.7), no sólo el umbral del test |

**Divergencia encontrada y resuelta sin reinterpretar métricas**: el resumen por asesor
exigido (nombre, cartera total, cartera activa, estancados, tiempo a asignación, tiempo a
primera gestión) no era construible con el contrato existente, que sólo exponía cartera
total/activa por asesor; los tiempos y el estancamiento existían únicamente como métricas
globales. Se resolvió **de forma aditiva**, agregando
`ExecutiveDashboardRepository.get_metricas_operacionales_por_asesor`, que agrupa por asesor
usando **exactamente las mismas definiciones** (predicado de estancamiento compartido,
primera asignación sobre `tpi.asignaciones`, primera gestión = primera nota humana o primer
cambio general de estado post-cutover, excluyendo la asignación). No se redefinió ninguna
métrica ni se inventó un valor: cuando el evento no existe para ningún lead del asesor, la
columna se reporta `N/D`, nunca `0`.

### 12.2 Archivos

| Componente | Archivo |
| --- | --- |
| Definiciones SQL compartidas (movimiento operativo, estancado, sin asignar) | `app/repositories/lead_activity_sql.py` (nuevo) |
| Presentación server-side de gráficos (barras, SVG, funnel, alertas, formatos CL) | `app/web/dashboard_presentation.py` (nuevo) |
| Template productivo | `app/web/templates/executive_dashboard.html` |
| Macros de sección (barras, tabla accesible, estados) | `app/web/templates/dashboard_macros.html` (nuevo) |
| Navegación CEO/CTO | `app/web/templates/base.html` |
| CSS (clases de §8 del diseño) | `app/web/static/css/app.css` |
| Ruta, filtros, estados de error, enlaces de alerta | `app/web/routes/dashboard.py` |
| Métricas por asesor y opciones de filtro | `app/repositories/executive_dashboard_repository.py`, `app/services/executive_dashboard_service.py` |
| Filtros reales del listado | `app/web/routes/leads.py`, `app/services/solicitud_service.py`, `app/repositories/solicitud_repository.py`, `app/web/templates/leads.html` |

### 12.3 Fidelidad al prototipo (alternativa C)

Los doce elementos de la Fase 2 del diseño están implementados en el mismo orden:
encabezado con indicador "CRM Lite · exclusivo CEO / CTO", filtros superiores, resumen
ejecutivo (KPIs), alertas operacionales, aviso de cobertura, análisis (evolución, casos
por estado, antigüedad, categorías MVP), funnel observable, resumen por asesor, y estados
vacío/parcial/error. Se conservan los tokens existentes (fondo claro, tarjetas blancas,
bordes y sombras suaves, turquesa `--accent`, jerarquía tipográfica), sin gradientes
decorativos ni animaciones; `prefers-reduced-motion` anula toda transición.

### 12.4 Ámbitos visibles y filtros

- La explicación de ámbitos es visible en la página: *"Las métricas de cartera representan
  la situación actual. El período seleccionado se aplica a ingresos, evolución y métricas
  de actividad."* Cada tarjeta KPI rotula además su propio ámbito.
- Formulario `GET` a `/dashboard` con período (desde/hasta), granularidad, asesor, AFP,
  estado, origen y fuente; botones **Aplicar** y **Limpiar**; sin JavaScript obligatorio.
- Los presets del prototipo ("Últimos 30 días") se traducen a **fechas explícitas**
  resueltas en el servidor, de modo que toda URL es reproducible y enlazable.
- Todo parámetro pasa por `DashboardFilters`; un rango inválido responde **400** con la
  página renderizada, los valores conservados y un mensaje claro, sin ejecutar consultas.

### 12.5 Gráficos server-rendered

HTML/CSS y SVG generados en el servidor; sin canvas, sin CDN, sin interpolación en
JavaScript. Cada gráfico lleva título, resumen textual, valores visibles, `n` y denominador
en cada porcentaje, tabla equivalente accesible (`<details>` + `<table>` con `<caption>` y
`scope`), estado de cero datos y escala segura cuando el máximo es cero. La serie de
evolución no fabrica puntos: con una sola observación dibuja un marcador sin polilínea, y
con todos los valores en cero queda plana sobre la línea base. Las etiquetas extremas del
eje usan `text-anchor` `start`/`end` para no recortarse.

### 12.6 Alertas, enlaces y paridad con el listado

Las dos alertas enlazan a `/leads?sin_asignar=1` y `/leads?estancado=1`, arrastrando los
mismos filtros de dimensión del dashboard (nunca el rango de fechas, que pertenece al otro
ámbito). El listado los implementa como filtros server-side reales reutilizando los
predicados compartidos de `lead_activity_sql`, de modo que la cantidad del listado coincide
con la de la alerta bajo el mismo contexto (verificado en integración). Se conservan el
enmascaramiento de PII y el RBAC existentes.

### 12.7 Rendimiento real (PostgreSQL local, volumen representativo)

Medición end-to-end de `build_executive_dashboard` con **2.000 leads y 12 asesores**
(`tests/integration/test_executive_dashboard_full.py::test_full_dashboard_latency_with_representative_volume`):

| Métrica | Valor observado |
| --- | --- |
| Sentencias SQL por render del dashboard | 18 |
| Sentencias SQL de las opciones de filtro | 4 |
| Tiempo del dashboard completo | 0,299 s |
| Tiempo de las opciones de filtro | 0,005 s |
| Consulta más lenta | `get_metricas_operacionales_por_asesor` (0,068 s) |
| Siguientes | `get_tiempo_primera_gestion` (0,068 s), `get_estancados_por_antiguedad` (0,048 s) |

Ausencia de N+1 verificada de forma explícita: el número de sentencias es **idéntico** con
20 leads / 2 asesores y con 400 leads / 12 asesores
(`test_full_dashboard_query_count_is_bounded_and_free_of_n_plus_1`). No se agregó ningún
índice nuevo: la latencia observada no lo justifica. `enable_seqscan` no se usa en runtime.

A **20.000 leads / 12 asesores** (benchmark reproducible
`scripts/benchmark_executive_dashboard.py`) la latencia total del render es **5,28–6,80 s**
con 18 sentencias constantes (sin N+1); las tres consultas más lentas (~1,3 s cada una)
tienen como costo dominante el **parsing regexp de las notas** en `leads.comentarios`
(`EXPLAIN`: Function Scan on `regexp_matches`). Clasificación del Reviewer (F6 de
`review-01.json`): riesgo (A) documentado, **no bloqueante para DEV** (acceso exclusivo
CEO/CTO, baja frecuencia). Follow-up concreto registrado y **no resuelto**: posible
normalización de las notas o read model futuro. El rendimiento no se declara resuelto.

### 12.7.1 Consistencia transaccional del render (snapshot read-only)

El dashboard se construye con ~18 consultas agregadas independientes. Para que un único
render no mezcle instantáneas distintas ante escrituras concurrentes (por ejemplo, que el
KPI total y la alerta de estancados discrepen entre sí), `build_executive_dashboard`
envuelve la construcción completa en `dashboard_read_snapshot`:

- **`REPEATABLE READ`**: toda consulta del render observa la base de datos tal como estaba
  en la primera sentencia de la transacción.
- **`READ ONLY`**: no se toma ningún bloqueo de escritura ni se puede emitir escritura.
- **savepoint por consulta**: cada agregado corre dentro de un `SAVEPOINT`, de modo que el
  fallo de una consulta no aborta la transacción compartida y se conserva el aislamiento
  por sección del servicio (la sección fallida se marca y el resto sigue renderizando).

Demostrado por `test_full_dashboard_reads_under_a_single_consistent_snapshot` (todo el
render usa exactamente una conexión del pool) y `test_dashboard_snapshot_does_not_see_concurrent_writes`
(una escritura confirmada a mitad del render no altera los conteos de la instantánea). La
instantánea se libera con `ROLLBACK` al salir y los defaults de sesión de la conexión se
restauran antes de devolverla al pool.

Riesgo operativo (F5 de `review-01.json`): `dashboard_read_snapshot` mantiene una única
conexión del pool durante todo el render (~5–7 s a volumen representativo), con una
transacción `REPEATABLE READ READ ONLY` que puede retener `xmin` y presionar el pool y el
autovacuum si el volumen o la frecuencia de uso crecen. Riesgo bajo hoy (acceso exclusivo
CEO/CTO, baja concurrencia esperada); seguimiento operacional, sin acción para esta tarea.

### 12.8 Pruebas

| Archivo | Cobertura |
| --- | --- |
| `tests/unit/test_executive_dashboard_presentation.py` (35) | formatos chilenos, anchos de barra seguros, escalera de antigüedad, series con 0/1/n puntos, disponibilidad del funnel y sus cuatro razones, alertas |
| `tests/unit/test_executive_dashboard_render.py` (38) | navegación CEO/CTO/otros roles, 403 sin estructura ni datos, render normal, KPIs, alertas con enlaces reales, ámbitos visibles, gráficos sin JS/CDN, porcentajes con `n`/base, estados desconocidos escapados, categorías MVP (sin género ni estado civil), funnel disponible/no disponible, tabla de asesores sin PII, cero datos, error parcial, error global seguro, filtros conservados, rango inválido, Aplicar/Limpiar |
| `tests/unit/test_leads_operational_filters.py` (15) | query params del listado, filtros preservados y limpiables, predicados compartidos, umbral configurable, RBAC y enmascaramiento intactos |
| `tests/integration/test_executive_dashboard_full.py` (11) | métricas por asesor, primera gestión sin cutover, PII ausente en el contrato, **paridad alerta ↔ listado** (sin asignar, estancado y con filtro combinado), opciones de filtro, conteo de sentencias y latencia real, y **consistencia transaccional del render** (una sola conexión/snapshot, aislamiento ante escritura concurrente) |
| `tests/integration/test_executive_dashboard_repository.py` (22) | cero datos, un lead, sin asesor, asignaciones inactivas, estados desconocidos, cartera activa, filtros, límites de fecha, zona horaria, granularidad, estancamiento, antigüedad, tiempos, **parser de notas** (zona horaria Santiago, cruce de medianoche, texto libre con apariencia de fecha ignorado, múltiples notas), **matriz del funnel/cutover** (sin cutover, período previo/cruzado/posterior, denominador cero, estados desconocidos, transición repetida, retorno de estado) y EXPLAIN |

Suite completa: **698 passed, 3 failed**. Los 3 fallos son los
`test_frozen_candidate_verification` preexistentes, que no se modificaron ni se debilitaron;
en esta sesión el síntoma observado es que `bash` no resuelve la ruta Windows del worktree
(`/bin/bash: C:desarrollos...: No such file or directory`, exit 127), la misma limitación
de invocación WSL ya registrada. Cobertura **88,70 %** (≥ 85).

### 12.9 Revisión visual y limitación registrada

Se renderizaron nueve escenarios con datos sintéticos **exclusivamente locales** (arnés de
scratchpad, nunca en la aplicación) y se auditó el DOM en los cuatro viewports exigidos:

| Viewport | Overflow global | Layout |
| --- | --- | --- |
| 1440×900 | 0 px | KPIs 4 columnas, análisis en dos columnas |
| 1024×768 | 0 px | KPIs 2 columnas, análisis en dos columnas |
| 768×1024 | 0 px | KPIs 2 columnas, análisis apilado |
| 375×812 | 0 px | Todo apilado; scroll horizontal contenido sólo en `.table-wrap` y `.timeseries-wrap` |

Sin texto por debajo de 11,5 px y sin objetivos táctiles de menos de 24 px de alto.
**Limitación**: la captura de pantalla del panel de navegador resultó intermitente con
viewports altos, por lo que la comparación pixel a pixel contra el prototipo no pudo
completarse para todas las secciones; la verificación se hizo con capturas parciales
(1440×900 y 375×812) más auditoría programática del DOM. Queda el checklist humano de §12.10.

### 12.10 Checklist humano pendiente

1. Abrir `/dashboard` como CEO y como CTO en DEV: la página carga y el enlace de navegación
   aparece.
2. Abrir `/dashboard` con un rol no autorizado y sin sesión: 403 real, sin datos.
3. Comparar visualmente contra `docs/prototypes/H3_3_4_dashboard_prototype.html` en
   1440×900, 1024×768, 768×1024 y 375×812.
4. Recorrer la página sólo con teclado: foco visible en filtros, rangos rápidos, enlaces de
   alerta y disclosures "Ver como tabla".
5. Aplicar filtros combinados y confirmar que la URL resultante reproduce la vista.
6. Probar un rango inválido (desde > hasta) y confirmar el mensaje.
7. Pulsar "Ver detalle" en cada alerta y confirmar que la cantidad del listado coincide con
   la de la alerta.
8. Confirmar que no aparece ningún RUT, nombre, teléfono ni correo de lead en la página ni
   en el código fuente servido.
9. Confirmar en DEV que `LEAD_STATE_HISTORY_CUTOVER` está configurada con la fecha exacta de
   aplicación de la migración 008 (ISO `YYYY-MM-DD`, sin zona horaria). Su ausencia falla de
   forma segura (funnel/primera gestión no disponibles), pero su exactitud no se verifica
   automáticamente (F4 de `review-01.json`). Las pruebas reales del default sin fecha
   inventada, valor ISO válido y valores inválidos existen en
   `tests/unit/test_h3_3_4_timeline_presentation.py` (validación del setting); la fecha real
   de cutover sigue siendo dato de despliegue pendiente, nunca inventado.

---

## 13. Remediación ronda 1 de revisión (review-01.json)

> Corrección de `evidence/H3.3.4/reviewer/review-01.json` (decision=REJECTED, cause=docs).
> Sin cambios funcionales; sin tocar migraciones 005/006/007/008, AWS/RDS, `requirements/**`,
> GitPython, RBAC ni definiciones métricas.

- **F1 (major, docs)** — **corregido**: la columna "Prueba automatizada" de §4
  (REQ-B-01..REQ-B-30) y las referencias de §3/§5/§7 citaban archivos planificados o
  inexistentes (`test_executive_dashboard.py`, `test_executive_dashboard_kpis.py`, etc.).
  Ahora citan los archivos y funciones reales (`test_executive_dashboard_{access,filters,
  presentation,render,service}.py` unit; `test_executive_dashboard_{full,repository}.py`
  integration), verificados contra el repositorio. El gate programático
  `tests/unit/test_h3_3_4_requirements_matrix_gate.py` impide la regresión.
- **F2 (minor, EXPLAIN forzado)** — **documentado como follow-up**: la aplicabilidad del
  índice 008 se demuestra con `enable_seqscan=off` (test real); las cifras "~40x/~90x a
  100k filas" son de la comparación forzada, no del plan normal. El `EXPLAIN (ANALYZE,
  BUFFERS)` real sin forzar a volumen representativo queda pendiente de adjuntar antes del
  cierre de la tarea (§11.6). No se agregan índices especulativos.
- **F3 (minor, tests 'unit' que requieren Postgres)** — **aceptado como follow-up**: los
  tests de `test_executive_dashboard_service.py` invocan `dashboard_read_snapshot()`
  directamente (no delegado al repositorio inyectable), por lo que requieren PostgreSQL.
  Sin cambio de código en esta ronda; follow-up sugerido por el Reviewer: que el repositorio
  (real o falso) posea la adquisición del snapshot para que la etiqueta "unit" sea fiel.
- **F4 (info, LEAD_STATE_HISTORY_CUTOVER)** — **agregado al checklist humano** (§12.10):
  verificar en DEV el valor exacto configurado. Se distingue la validación del setting
  (automatizada, `test_h3_3_4_timeline_presentation.py`) de la configuración efectiva en AWS
  DEV (dato de despliegue pendiente, sin fecha inventada).
- **F5 (info, transacción REPEATABLE READ prolongada)** — **riesgo documentado**, sin
  acción: relación con latencia, pool y vacuum registrada en §12.7.1.
- **F6 (info, rendimiento)** — **preservado**: 5,28–6,80 s a 20.000 leads/12 asesores,
  parsing regexp de comentarios como causa principal, clasificación (A) no bloqueante para
  DEV; follow-up de normalización/read model registrado y no resuelto (§12.7).
