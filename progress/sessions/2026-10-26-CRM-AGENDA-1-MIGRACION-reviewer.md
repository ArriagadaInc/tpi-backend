# Sesion archivada: CRM-AGENDA-1-MIGRACION-reviewer

- Archivada: 2026-10-26T20:03:15Z
- Estado: REVIEWING

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: REVIEWING (rol: reviewer)
- Tarea: CRM-AGENDA-1-MIGRACION
- Proximo paso: Reviewer: revisar SHA exacto, CI verde, registrar review y review_approve o review_reject
- Ultima transicion: start_review (READY_FOR_REVIEW -> REVIEWING)
- Actualizado: 2026-10-26T20:00:07Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-26-CRM-AGENDA-1-MIGRACION-developer.md

## Estado reciente
- DECISION (REVIEWER, 2026-10-26, sesion claude-202610261959-reviewer-sup4c3b46): CRM-AGENDA-1-MIGRACION APPROVED sobre PR #138 SHA c717a04d5d2d (tree 8cbb82ec9c12). CI run 40390284229 verde en el SHA exacto (8 tests de integracion de 010 PASSED, cobertura 92%); AC-1 a AC-5 cumplidos; AC-6 humano pendiente. Hallazgos no bloqueantes: 2 minor en scripts/dev_usuarios.py (marcar-coordinadores sin chequeo de filas afectadas; socios resuelve por nombre y fija rol socio) y 3 info. Tras el merge: merged_non_fast_path -> BLOCKED_HUMAN (clase D). Evidencia: evidence/CRM-AGENDA-1-MIGRACION/reviewer/review-01.json.
- DECISION (DEVELOPER, 2026-10-26): CRM-AGENDA-1-MIGRACION implementada y entregada a revision (PR #138, rama harness/CRM-AGENDA-1-MIGRACION-agenda, SHA c717a04d5d2d). Migracion 010 (forward + reversa), bootstrap de pruebas, subcomandos humanos socios/marcar-coordinadores y documentacion. CI verde (Tests 91.68% cobertura, Lint & Format, Security Audit, Docker Build, Release Tooling Validation). AC-1 a AC-5 cubiertos por pruebas; AC-6 (aplicacion en AWS DEV por el humano) pendiente de verificacion humana. Evidencia: evidence/CRM-AGENDA-1-MIGRACION/developer/developer-01.json.
- DECISION (ORQUESTADOR INTERACTIVO, 2026-10-26): CRM-PERFILES-1-RBAC cerrada en DONE (verificacion PASS, AC-8 aceptado). Release ba53777 (PR 132) desplegado en DEV como h3-crm-perfiles-1-rbac-ba53777-domainlocked-r1; una ronda de rework (el Reviewer pidio la matriz de pruebas completa y la entrada de BITACORA). Pendiente del humano: desmontar las cuentas de prueba coordinador.ejemplo1 y coordinador.ejemplo2 del secreto tpi/dev/auth-users con scripts/dev_usuarios.py quitar. La tarea HARNESS-LOGS-FALSOS-POSITIVOS-CADDY sigue en el backlog. Detalle en docs/BITACORA.md.
- NOTA (ORQUESTADOR INTERACTIVO, 2026-10-26) PARA CRM-AGENDA-1-MIGRACION: chequeo de solo lectura del humano en AWS DEV (PostgreSQL 17.9): tpi_admin es miembro de rds_superuser y btree_gist 1.7 esta disponible (no instalada), asi que la restriccion EXCLUDE es viable. Forma REAL de tpi.citas en DEV (0 filas): id_cita uuid PK default gen_random_uuid(); id_lead uuid NOT NULL FK a tpi.leads(id_lead); id_asesor uuid NULL FK a tpi.asesores(id_asesor); fecha_hora timestamptz NOT NULL; canal varchar NOT NULL default 'Google Meet'; estado_cita varchar NOT NULL default 'agendada'; link_reunion text NULL; created_at timestamptz NOT NULL default now(); sin CHECK ni otros indices; las FK son NO ACTION. Usala como base de tpi.citas en scripts/init_test_database.py (tambien esta en docs/database/02_PHYSICAL_SCHEMA.md). tpi.asesores en DEV: id_asesor, nombre, email NULL, rol default 'asesor', estado_disponibilidad default 'activo', especialidad NULL, carga_activa default 0, created_at; hoy 6 asesores activos con rol asesor. Privilegios de tpi_app: citas ninguno, asesores SELECT, auditoria INSERT.

## Bloqueos
- Ninguno.
