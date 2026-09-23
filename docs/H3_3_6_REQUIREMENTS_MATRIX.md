# H3.3.6 — Matriz de Cobertura de Requisitos (Requirements Coverage Gate)

Tarea: `H3.3.6 Exportacion ejecutiva XLSX segura`
Baseline: `origin/main@78bf33bcb946fc442a8e5488cdf0d2f89fd190c2`
Rol: Developer (runtime deepseek). Estado al crear esta matriz: `DEVELOPING`.

## Propósito

Trazabilidad completa requisito (F1-F10/seguridad) → AC → componente previsto →
prueba automatizada → smoke/evidencia. Todo requisito tiene, como mínimo, un AC,
un componente de implementación previsto y una prueba automatizada o un
smoke/evidencia reproducible. Si alguno quedara sin cobertura, el gate se considera
`FAIL` y el desarrollo se detiene (BLOCKER).

## Leyenda

- `T` = prueba automatizada (unit / integration).
- `H` = verificación humana (smoke autenticado en AWS DEV, fases posteriores).
- `D` = artefacto documental/estático verificable (matrices, gate programático).

## Matriz

| # | Requisito | AC | Componente previsto | Prueba automatizada | Smoke / Evidencia |
| --- | --- | --- | --- | --- | --- |
| 1 | F1: botón Exportar XLSX visible solo para CEO/CTO (sin HTML residual) | AC-1, AC-15 | `app/web/templates/leads.html` + flag `can_export_xlsx` (contexto) | `tests/unit/test_h3_3_6_export_web.py::test_ceo_and_cto_see_export_button`, `tests/unit/test_h3_3_6_export_web.py::test_non_superuser_roles_do_not_see_button` | AC-18 (smoke humano) |
| 2 | F2: autorización server-side CEO/CTO; otros roles autenticados → 403; anónimo → canónico | AC-2, AC-13, AC-15 | ruta `GET /leads/export.xlsx` (`is_superuser` antes de consultar) | `tests/unit/test_h3_3_6_export_web.py::test_non_superuser_gets_403`, `tests/unit/test_h3_3_6_export_web.py::test_anonymous_redirects_to_login`, `tests/unit/test_h3_3_6_export_web.py::test_ceo_and_cto_authorized_download`, `tests/unit/test_h3_3_6_export_web.py::test_non_superuser_rejected_before_any_repository_access`, `tests/integration/test_h3_3_6_export_full.py::test_ceo_export_and_advisor_403` | AC-18 |
| 3 | F3: reutiliza exactamente el contrato server-side del listado (filtros y orden determinista), sin implementación paralela | AC-3, AC-4 | `SolicitudService.export_leads_xlsx` + `SolicitudRepository._build_crm_query_filters` reutilizado (`count_crm_solicitudes` / `get_crm_solicitudes_export`) | `tests/unit/test_h3_3_6_export_service.py::test_filters_forwarded_to_repository`, `tests/integration/test_h3_3_6_export_full.py::test_export_respects_combined_filters` | AC-18 |
| 4 | F4: allowlist explícita y revisada de columnas (sin descubrimiento dinámico) | AC-5, AC-6 | `app/services/xlsx_export.py::EXPORT_COLUMNS` + `docs/H3_3_6_EXPORT_COLUMNS.md` | `tests/unit/test_h3_3_6_xlsx_export_builder.py::test_headers_match_allowlist_exactly`, `tests/unit/test_h3_3_6_export_service.py::test_allowlist_drops_extra_row_keys`, `tests/unit/test_h3_3_6_requirements_matrix_gate.py` | AC-18 |
| 5 | F5: XLSX válido (una hoja, encabezados constantes, freeze, autofiltro, anchos, tipos nativos) | AC-7, AC-9 | `app/services/xlsx_export.py::build_xlsx_workbook` | `tests/unit/test_h3_3_6_xlsx_export_builder.py::test_build_returns_valid_xlsx_single_sheet`, `tests/unit/test_h3_3_6_xlsx_export_builder.py::test_freeze_panes_and_autofilter`, `tests/unit/test_h3_3_6_xlsx_export_builder.py::test_column_widths_configured`, `tests/unit/test_h3_3_6_xlsx_export_builder.py::test_numbers_native_clp_format`, `tests/unit/test_h3_3_6_xlsx_export_builder.py::test_dates_native_date_cells`, `tests/unit/test_h3_3_6_xlsx_export_builder.py::test_timezone_aware_timestamp_converted_to_crm_local_naive` | AC-18 |
| 6 | F6: formula injection neutralizado (`=`, `+`, `-`, `@`), sin alterar fechas ni montos | AC-8 | `app/services/xlsx_export.py::sanitize_cell_text` | `tests/unit/test_h3_3_6_xlsx_export_builder.py::test_formula_trigger_prefixes_neutralized`, `tests/unit/test_h3_3_6_xlsx_export_builder.py::test_no_formula_cells` | — |
| 7 | F7: generación efímera (memoria, sin persistencia) + headers MIME XLSX, Content-Disposition, Cache-Control no-store, X-Content-Type-Options nosniff | AC-11, AC-13 | ruta + `build_xlsx_workbook` (BytesIO, sin archivo temporal) | `tests/unit/test_h3_3_6_export_web.py::test_response_security_headers_and_filename` | AC-18 |
| 8 | F8: límite máximo constante, conteo previo y aborto sin truncamiento | AC-10 | `EXPORT_MAX_ROWS` + `SolicitudRepository.count_crm_solicitudes` + `ExportLimitExceededError` | `tests/unit/test_h3_3_6_export_service.py::test_limit_exceeded_aborts_before_fetch`, `tests/unit/test_h3_3_6_export_web.py::test_limit_exceeded_clear_message` | AC-18 |
| 9 | F9: auditoría funcional exitosa sin PII (actor/role/timestamp/filtros sanitizados/rows/formato) | AC-12, AC-14 | `SolicitudRepository.record_xlsx_export_event` (INSERT append-only en `tpi.auditoria`) | `tests/unit/test_h3_3_6_export_service.py::test_audit_event_sanitized_without_search_text`, `tests/integration/test_h3_3_6_export_full.py::test_export_writes_audit_event_without_pii`, `tests/integration/test_h3_3_6_export_full.py::test_export_does_not_mutate_leads` | AC-18 |
| 10 | F10: UX (botón integrado sin romper Actualizar/Limpiar, mensajes claros de cero/exceso/error) | AC-1, AC-10 | `leads.html` (enlace con `export_url` desde `current_query`) + página de error de límite | `tests/unit/test_h3_3_6_export_web.py::test_ceo_and_cto_see_export_button`, `tests/unit/test_h3_3_6_export_web.py::test_limit_exceeded_clear_message` | AC-18 |
| 11 | Seguridad/PII: sin `raw_payload`, secretos, tokens, metadata interna ni campos fuera de allowlist | AC-6, AC-12, AC-13 | allowlist explícita + auditoría sanitizada (sin `search` libre) | `tests/unit/test_h3_3_6_export_service.py::test_allowlist_drops_extra_row_keys`, `tests/unit/test_h3_3_6_export_service.py::test_audit_event_sanitized_without_search_text`, `tests/integration/test_h3_3_6_export_full.py::test_export_writes_audit_event_without_pii` | AC-18 |
| 12 | Regresión: CEO/CTO conservan capacidades; advisor mantiene cartera aislada y sin exportación | AC-15 | sin cambios en `is_superuser`/`can_view_full_pii`/portfolio; exportación solo superuser | `tests/unit/test_rbac_superusers.py`, `tests/integration/test_h3_3_5_advisor_portfolio.py`, `tests/integration/test_h3_3_6_export_full.py::test_ceo_export_and_advisor_403` | AC-18 |
| 13 | Cobertura total del proyecto ≥ 85% | AC-17 | CI `pytest --cov=app --cov-fail-under=85` | job CI (sin pytest individual aplicable) | — |
| 14 | Smoke humano AWS DEV (CEO descarga, CTO descarga, advisor 403, filtros, apertura visual, tipos, ausencia de prohibidos, auditoría segura, logs sin PII) | AC-18 | `docs/H3_3_6_REQUIREMENTS_MATRIX.md` (este documento) + runbook de verificación | — | AC-18 (humano, `pending_verification`) |

## Cobertura de AC

| AC | Descripción resumida | Cobertura |
| --- | --- | --- |
| AC-1 | Botón Exportar XLSX solo CEO/CTO (sin HTML residual) | `tests/unit/test_h3_3_6_export_web.py::test_ceo_and_cto_see_export_button`, `test_non_superuser_roles_do_not_see_button` |
| AC-2 | CEO/CTO descargan; otros roles autenticados → 403 real server-side; anónimo canónico | `tests/unit/test_h3_3_6_export_web.py::test_non_superuser_gets_403`, `test_anonymous_redirects_to_login`, `test_ceo_and_cto_authorized_download` |
| AC-3 | Reutiliza contrato server-side del listado; orden determinista | `tests/unit/test_h3_3_6_export_service.py::test_filters_forwarded_to_repository`, `tests/integration/test_h3_3_6_export_full.py::test_export_respects_combined_filters` |
| AC-4 | Todos los resultados coincidentes, sin paginación | `tests/integration/test_h3_3_6_export_full.py::test_export_ignores_pagination_and_contains_all_rows` |
| AC-5 | Allowlist coincide con matriz revisada | `tests/unit/test_h3_3_6_xlsx_export_builder.py::test_headers_match_allowlist_exactly` + gate |
| AC-6 | Sin campos prohibidos (raw_payload, secretos, metadata interna) | `tests/unit/test_h3_3_6_export_service.py::test_allowlist_drops_extra_row_keys` + gate |
| AC-7 | XLSX válido (hoja, encabezados, freeze, autofiltro, anchos, tipos, CLP, texto con ceros) | `tests/unit/test_h3_3_6_xlsx_export_builder.py` (múltiples, incl. `test_timezone_aware_timestamp_converted_to_crm_local_naive`) + AC-18 |
| AC-8 | Formula injection neutralizado (4 prefijos), sin alterar fechas/montos | `tests/unit/test_h3_3_6_xlsx_export_builder.py::test_formula_trigger_prefixes_neutralized`, `test_no_formula_cells` |
| AC-9 | Resultado vacío → XLSX válido con encabezados y cero filas | `tests/unit/test_h3_3_6_xlsx_export_builder.py::test_empty_result_headers_only`, `tests/integration/test_h3_3_6_export_full.py::test_empty_export_returns_valid_file` |
| AC-10 | Límite máximo constante; exceso aborta antes de generar con mensaje claro | `tests/unit/test_h3_3_6_export_service.py::test_limit_exceeded_aborts_before_fetch`, `tests/unit/test_h3_3_6_export_web.py::test_limit_exceeded_clear_message` |
| AC-11 | Generación efímera + headers MIME/disposition/no-store/nosniff | `tests/unit/test_h3_3_6_export_web.py::test_response_security_headers_and_filename` |
| AC-12 | Auditoría exitosa sin PII (actor/role/timestamp/filtros sanitizados/rows/formato) | `tests/unit/test_h3_3_6_export_service.py::test_audit_event_sanitized_without_search_text`, `tests/integration/test_h3_3_6_export_full.py::test_export_writes_audit_event_without_pii` |
| AC-13 | No autorizados rechazados antes de consulta/construcción; sin fuga | `tests/unit/test_h3_3_6_export_web.py::test_non_superuser_gets_403`, `test_non_superuser_rejected_before_any_repository_access` |
| AC-14 | No altera datos; única escritura es el evento de exportación | `tests/integration/test_h3_3_6_export_full.py::test_export_does_not_mutate_leads` |
| AC-15 | CEO/CTO conservan capacidades; advisor cartera aislada sin exportación | `tests/unit/test_rbac_superusers.py`, `tests/integration/test_h3_3_5_advisor_portfolio.py`, `tests/integration/test_h3_3_6_export_full.py::test_ceo_export_and_advisor_403` |
| AC-16 | Pruebas cubren autorización, filtros, paginación, allowlist, tipos, Unicode, ceros, nulos, formula injection, auditoría, vacío, límite, headers/nombre, fallo+cleanup, regresión | conjunto de `tests/unit/test_h3_3_6_*` + `tests/integration/test_h3_3_6_export_full.py` |
| AC-17 | Cobertura total ≥ 85% | job CI `pytest --cov-fail-under=85` |
| AC-18 | Smoke humano AWS DEV | `pending_verification` (humano) |

## Resultado del Requirements Coverage Gate

- Estado: **PASS**
- Todo requisito listado en el enunciado tiene AC, componente previsto y prueba
  automatizada o smoke/evidencia reproducible.
- No se detectó ningún requisito sin AC, sin implementación prevista, sin prueba
  automatizada cuando corresponde o sin evidencia reproducible.
- No hay BLOCKER de cobertura.

*Gate registrado como paso de Developer (evidencia `developer.json`).*
