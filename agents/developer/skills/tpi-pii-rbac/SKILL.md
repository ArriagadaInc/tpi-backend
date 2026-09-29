---
name: tpi-pii-rbac
role: developer
load_when: "DEVELOPING cuando la tarea toca roles, masking o vistas con datos personales"
sources: [release_contract_v2, database_docs, h33_web_ux, technical_decisions]
---

# tpi-pii-rbac

## 1. Cuando se carga
Cambios en `app/security`, `app/auth`, `app/web/routes`, templates con RUT/email/telefono o roles.

## 2. Puede
- Aplicar masking server-side por rol antes de renderizar (`can_view_full_pii`: ceo, cto).
- Agregar tests que inspeccionen el HTML renderizado por rol.

## 3. No puede
- Enmascarar solo en el cliente (CSS/JS) o enviar PII completa y ocultarla visualmente.
- Depender de un flag global que ignore el rol cuando la regla es por rol.
- Registrar PII en logs, eventos o evidencia.
- Leer `AUTH_USERS_JSON` o crear usuarios reales.

## 4. Precondiciones
- Matriz de roles de `docs/H3_3_CRM_LITE_WEB_UX.md` seccion 4 y contrato seccion 9 leidos.

## 5. Comandos y herramientas
- Tests de seguridad: `pytest tests/security tests/integration -q`.
- Usuarios ficticios de prueba con hashes generados en el test, nunca reales.

## 6. Evidencia obligatoria
- Tests por rol (ceo/cto vs restringido) sobre bandeja y detalle que verifican ausencia de PII
  completa en el HTML servido.
- Criterios humanos marcados `pending_verification` para el smoke autenticado en DEV.

## 7. STOP
- La regla de negocio de visibilidad es ambigua o contradice documentacion: reportar.

## 8. Fuentes
- `docs/cicd/TPI_Contrato_CICD_AWS_v2.md` seccion 9 (smoke minimo H3.3.1).
- `docs/database/05_SECURITY_ACCESS.md`; `docs/DECISIONES_TECNICAS.md` decision 4 (superada por server-side).
