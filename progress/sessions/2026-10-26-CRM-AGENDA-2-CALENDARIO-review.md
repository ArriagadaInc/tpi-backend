# Sesion archivada: CRM-AGENDA-2-CALENDARIO-review

- Archivada: 2026-10-26T21:26:29Z
- Estado: REVIEWING

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: REVIEWING (rol: reviewer)
- Tarea: CRM-AGENDA-2-CALENDARIO
- Proximo paso: Reviewer: revisar SHA exacto, CI verde, registrar review y review_approve o review_reject
- Ultima transicion: start_review (READY_FOR_REVIEW -> REVIEWING)
- Actualizado: 2026-10-26T21:22:50Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-26-CRM-AGENDA-2-CALENDARIO-developer.md

## Estado reciente
- DECISION (REVIEWER, 2026-10-26, sesion claude-202610262122-reviewer-sup3d2776): CRM-AGENDA-2-CALENDARIO REJECTED en 9627fca (PR #140, tree 527a086, CI verde). Blocker: la regla de lead activo (AC-1) no se aplica en ninguna capa (LEAD_INACTIVO_PARA_AGENDA sin uso; agendar reabre leads cerrados/perdidos). Major: matriz de permisos AC-6 incompleta (test_agendar_readonly_denegado pasa por CSRF, no por perfil) y falta prueba sobre el HTML de GET /agenda para AC-4. Minors: vista semana visible en movil, inferencia del dueno por orden de validacion, motivo libre en auditoria. Evidencia: evidence/CRM-AGENDA-2-CALENDARIO/reviewer/review-01.json.
- DECISION (DEVELOPER, 2026-10-26): CRM-AGENDA-1-MIGRACION implementada y entregada a revision (PR #138, rama harness/CRM-AGENDA-1-MIGRACION-agenda, SHA c717a04d5d2d). Migracion 010 (forward + reversa), bootstrap de pruebas, subcomandos humanos socios/marcar-coordinadores y documentacion. CI verde (Tests 91.68% cobertura, Lint & Format, Security Audit, Docker Build, Release Tooling Validation). AC-1 a AC-5 cubiertos por pruebas; AC-6 (aplicacion en AWS DEV por el humano) pendiente de verificacion humana. Evidencia: evidence/CRM-AGENDA-1-MIGRACION/developer/developer-01.json.
- DECISION (ORQUESTADOR INTERACTIVO, 2026-10-26): CRM-PERFILES-1-RBAC cerrada en DONE (verificacion PASS, AC-8 aceptado). Release ba53777 (PR 132) desplegado en DEV como h3-crm-perfiles-1-rbac-ba53777-domainlocked-r1; una ronda de rework (el Reviewer pidio la matriz de pruebas completa y la entrada de BITACORA). Pendiente del humano: desmontar las cuentas de prueba coordinador.ejemplo1 y coordinador.ejemplo2 del secreto tpi/dev/auth-users con scripts/dev_usuarios.py quitar. La tarea HARNESS-LOGS-FALSOS-POSITIVOS-CADDY sigue en el backlog. Detalle en docs/BITACORA.md.
- NOTA (ORQUESTADOR INTERACTIVO, 2026-10-26) PARA CRM-AGENDA-1-MIGRACION: chequeo de solo lectura del humano en AWS DEV (PostgreSQL 17.9): tpi_admin es miembro de rds_superuser y btree_gist 1.7 esta disponible (no instalada), asi que la restriccion EXCLUDE es viable. Forma REAL de tpi.citas en DEV (0 filas): id_cita uuid PK default gen_random_uuid(); id_lead uuid NOT NULL FK a tpi.leads(id_lead); id_asesor uuid NULL FK a tpi.asesores(id_asesor); fecha_hora timestamptz NOT NULL; canal varchar NOT NULL default 'Google Meet'; estado_cita varchar NOT NULL default 'agendada'; link_reunion text NULL; created_at timestamptz NOT NULL default now(); sin CHECK ni otros indices; las FK son NO ACTION. Usala como base de tpi.citas en scripts/init_test_database.py (tambien esta en docs/database/02_PHYSICAL_SCHEMA.md). tpi.asesores en DEV: id_asesor, nombre, email NULL, rol default 'asesor', estado_disponibilidad default 'activo', especialidad NULL, carga_activa default 0, created_at; hoy 6 asesores activos con rol asesor. Privilegios de tpi_app: citas ninguno, asesores SELECT, auditoria INSERT.
- 2026-10-26: Tarea CRM-AGENDA-1-MIGRACION cerrada; resumen en tasks/completed/CRM-AGENDA-1-MIGRACION.yaml
- NOTA (ORQUESTADOR INTERACTIVO, 2026-10-26) PARA CRM-AGENDA-2-CALENDARIO: la migracion 010 YA esta en main (PR 138) y aplicada en AWS DEV: tpi.citas tiene fecha_hora_fin, agendada_por_subject, agendada_por_nombre, nota, motivo_cancelacion, updated_at, id_asesor NOT NULL, estado_cita con CHECK (agendada, realizada, no_asistio, cancelada), una agendada por lead y EXCLUDE para que un responsable no se pise; tpi.asesores tiene atiende_reuniones. Los Socios son filas de asesores con rol 'socio' y atiende_reuniones = true (Diego y Alvaro Operaciones); los Coordinadores conservan rol 'asesor' con la marca en true; el Runner tiene la marca en false. scripts/init_test_database.py ya trae la forma final para las pruebas. Pistas de reutilizacion (verificalas): (1) SolicitudRepository.update_lead_status (app/repositories/solicitud_repository.py, estatico, abre SU PROPIA conexion y transaccion: SELECT ... FOR UPDATE del lead, comprobacion de cartera con advisor_scope, UPDATE de tpi.leads y auditoria cambio_estado_lead) NO sirve tal cual para el AC-3, que exige la misma transaccion que la reunion: extrae su logica a una funcion que reciba un cursor ya abierto y haz que update_lead_status y la agenda la usen, sin cambiar su comportamiento ni debilitar sus pruebas. (2) Permisos del servicio: SolicitudService.update_lead_status (rechazo del Runner para reunion_realizada, ficha_generada y cerrado), has_portfolio_scope y resolve_advisor_identity; en la web, _can_write y _validate_csrf_token (app/web/routes/leads.py). (3) Menu: app/web/templates/base.html (barra superior). (4) Zona horaria: ZoneInfo('America/Santiago') como en app/repositories/executive_dashboard_repository.py.

## Bloqueos
- Ninguno.
