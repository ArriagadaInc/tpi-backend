---
name: tpi-security-pii-review
role: reviewer
load_when: "REVIEWING"
sources: [release_contract_v2, database_docs, technical_decisions, aws_policy]
---

# tpi-security-pii-review

## 1. Cuando se carga
Toda revision; profundidad maxima si el diff toca auth, roles, masking, templates o logging.

## 2. Puede
- Ejecutar tests de seguridad y bandit; inspeccionar HTML renderizado en tests por rol.

## 3. No puede
- Probar con credenciales reales, leer `.env*` o secretos.

## 4. Precondiciones
- Matriz de roles y regla de PII (CEO/CTO completa; resto enmascarada server-side) conocidas.

## 5. Comandos y herramientas
- `pytest tests/security -q`, `bandit -r app/ --severity-level medium --confidence-level medium`.
- Busqueda de secretos en el diff (claves, hashes Argon2, URLs prefirmadas).

## 6. Evidencia obligatoria
- Checks: `pii_server_side`, `no_pii_in_html_for_restricted_roles`, `csrf_and_session`,
  `no_secrets_in_diff`, `safe_logging`, `authz_fail_closed`.

## 7. STOP
- Cualquier fuga de PII o secreto: REJECTED con severidad blocker.

## 8. Fuentes
- `docs/cicd/TPI_Contrato_CICD_AWS_v2.md` secciones 9 y 11.
- `docs/database/05_SECURITY_ACCESS.md`; `docs/AWS_DEPLOYMENT_POLICY.md` principio 11 (provisional).
