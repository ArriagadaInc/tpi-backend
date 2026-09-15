---
name: aws-failure-analysis
role: deployer
load_when: "DEPLOYING/VERIFYING ante error, DEPLOY_FAILED, VERIFY_FAILED, ROLLING_BACK"
sources: [aws_lessons_extracts, release_contract_v1_extract, aws_policy, release_contract_v2, eb_runbook]
---

# aws-failure-analysis

## 1. Cuando se carga
Ante cualquier error AWS, AccessDenied, timeout o verificacion fallida.

## 2. Puede
- Inventario read-only de residuos y clasificacion del fallo.
- Decidir entre `start_rollback` (si aplica la autorizacion condicionada) y `escalate`.

## 3. No puede
- Reintentar, limpiar, borrar, agregar permisos, cambiar de principal o de capa (DNS/DB/secretos/codigo).

## 4. Precondiciones
- Evidencia del paso fallido (deployment/verification) registrada.

## 5. Comandos y herramientas
Orden de diagnostico: estado EB -> eventos EB -> (CloudTrail: humano) -> logs -> resumenes.
- `aws_guard.py elasticbeanstalk describe-environments ...`, `describe-events ...`,
  `describe-application-versions ...`, `s3api head-object ...`.
Clasificacion: `infrastructure` (degradacion/inconsistencia de runtime), `functional` (defecto de
producto), `observability` (no hay evidencia), mas `contract drift` / `AWS service behavior` en el texto.
Residuos: ninguno / objeto S3 / Application Version / environment en transicion.

## 6. Evidencia obligatoria
`failure-*.json`: action, resource, principal (sin ARN completo), error redactado, state,
recommendation, residues, access_denied.

## 7. STOP
- Siempre termina en `escalate` -> BLOCKED_HUMAN, salvo rollback condicionado permitido.
- Mismo error de infraestructura dos veces: no hay tercer intento.

## 8. Fuentes
- `docs/cicd/LECCIONES_DEPLOY_AWS_H3_2_H3_3.md` LL-04, LL-06 y checklist post-fallo.
- `docs/cicd/CONTRATO_CICD_AWS_V1_EXTRACTO.md` puntos 5-7; `docs/AWS_DEPLOYMENT_POLICY.md` seccion 4.
- `docs/DEV_EB_DEPLOYMENT_RUNBOOK.md` matriz de fallos (tecnica; IDs historicos no aplican).
