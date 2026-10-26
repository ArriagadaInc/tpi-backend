# Sesion archivada: CRM-AGENDA-1-MIGRACION-developer

- Archivada: 2026-10-26T19:59:03Z
- Estado: DEVELOPING

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: DEVELOPING (rol: developer)
- Tarea: CRM-AGENDA-1-MIGRACION
- Proximo paso: Developer: implementar, correr gates, abrir/actualizar PR, registrar evidencia y submit_for_review
- Ultima transicion: start_development (NEW -> DEVELOPING)
- Actualizado: 2026-10-26T19:09:12Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-26-CRM-PERFILES-1-RBAC-closure.md

## Estado reciente
- DECISION (DEVELOPER, 2026-10-26): CRM-AGENDA-1-MIGRACION implementada y entregada a revision (PR #138, rama harness/CRM-AGENDA-1-MIGRACION-agenda, SHA c717a04d5d2d). Migracion 010 (forward + reversa), bootstrap de pruebas, subcomandos humanos socios/marcar-coordinadores y documentacion. CI verde (Tests 91.68% cobertura, Lint & Format, Security Audit, Docker Build, Release Tooling Validation). AC-1 a AC-5 cubiertos por pruebas; AC-6 (aplicacion en AWS DEV por el humano) pendiente de verificacion humana. Evidencia: evidence/CRM-AGENDA-1-MIGRACION/developer/developer-01.json.

- DECISION (ORQUESTADOR INTERACTIVO, 2026-10-26): CRM-PERFILES-1-RBAC cerrada en DONE (verificacion PASS, AC-8 aceptado). Release ba53777 (PR 132) desplegado en DEV como h3-crm-perfiles-1-rbac-ba53777-domainlocked-r1; una ronda de rework (el Reviewer pidio la matriz de pruebas completa y la entrada de BITACORA). Pendiente del humano: desmontar las cuentas de prueba coordinador.ejemplo1 y coordinador.ejemplo2 del secreto tpi/dev/auth-users con scripts/dev_usuarios.py quitar. La tarea HARNESS-LOGS-FALSOS-POSITIVOS-CADDY sigue en el backlog. Detalle en docs/BITACORA.md.

- NOTA (ORQUESTADOR INTERACTIVO, 2026-10-26) PARA CRM-AGENDA-1-MIGRACION: chequeo de solo lectura del humano en AWS DEV (PostgreSQL 17.9): tpi_admin es miembro de rds_superuser y btree_gist 1.7 esta disponible (no instalada), asi que la restriccion EXCLUDE es viable. Forma REAL de tpi.citas en DEV (0 filas): id_cita uuid PK default gen_random_uuid(); id_lead uuid NOT NULL FK a tpi.leads(id_lead); id_asesor uuid NULL FK a tpi.asesores(id_asesor); fecha_hora timestamptz NOT NULL; canal varchar NOT NULL default 'Google Meet'; estado_cita varchar NOT NULL default 'agendada'; link_reunion text NULL; created_at timestamptz NOT NULL default now(); sin CHECK ni otros indices; las FK son NO ACTION. Usala como base de tpi.citas en scripts/init_test_database.py (tambien esta en docs/database/02_PHYSICAL_SCHEMA.md). tpi.asesores en DEV: id_asesor, nombre, email NULL, rol default 'asesor', estado_disponibilidad default 'activo', especialidad NULL, carga_activa default 0, created_at; hoy 6 asesores activos con rol asesor. Privilegios de tpi_app: citas ninguno, asesores SELECT, auditoria INSERT.

## Bloqueos
- Ninguno.
