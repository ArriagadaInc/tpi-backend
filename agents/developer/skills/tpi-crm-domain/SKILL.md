---
name: tpi-crm-domain
role: developer
load_when: "DEVELOPING cuando la tarea toca estados CRM, asignaciones, seguimiento o auditoria"
sources: [database_docs, h33_web_ux, handoff_h33]
---

# tpi-crm-domain

## 1. Cuando se carga
Cambios en `app/models/crm_states.py`, `app/models/lead_assignment.py`, asignacion o auditoria.

## 2. Puede
- Implementar la asignacion inicial: validar usuario, lead y asesor; lock del lead; verificar
  asignacion activa; insertar asignacion; `estado_lead = asignado`; auditar; todo en una transaccion.

## 3. No puede
- Ofrecer `asignado` en el selector generico de estados.
- Reasignar, autoasignar o cerrar asignaciones previas en silencio (fuera de alcance H3.3).
- Usar `display_name` como `asignado_por` (usar `AuthenticatedUser.subject`).
- Escribir variantes de `estado_asignacion` distintas de `activa`.

## 4. Precondiciones
- `docs/database/03_BUSINESS_RULES.md` leido completo.

## 5. Comandos y herramientas
- `pytest tests/unit/test_crm_states.py tests/unit/test_solicitud_assignment_service.py tests/integration/test_web_crm_lite.py -q`

## 6. Evidencia obligatoria
- Tests de conflicto (asignacion activa existente) y rollback.
- Criterio de smoke de asignacion en DEV como `pending_verification`.

## 7. STOP
- La tarea requiere reasignacion, SLA o automatizacion no especificadas.

## 8. Fuentes
- `docs/database/03_BUSINESS_RULES.md`, `docs/H3_3_CRM_LITE_WEB_UX.md` seccion 6.
- `docs/BITACORA.md` entrada 2026-09-12 (deuda H3.3.1).
