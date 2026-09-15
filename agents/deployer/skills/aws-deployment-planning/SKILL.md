---
name: aws-deployment-planning
role: deployer
load_when: "PREPARING_DEPLOYMENT (cierre)"
sources: [release_contract_v2, aws_policy, aws_lessons_extracts]
---

# aws-deployment-planning

## 1. Cuando se carga
Al terminar STAGING, para producir el candidate completo y el paquete que vera el humano.

## 2. Puede
- Componer `candidate-*.json` con plan de cutover, plan de rollback y plan de smoke.

## 3. No puede
- Solicitar la aprobacion o avanzar con datos no verificados.
- Planificar acciones fuera de la allowlist de DEPLOYING/ROLLING_BACK.

## 4. Precondiciones
- Preflight PASS, candidate construido, S3 y AV stageados, clase de tarea A o B.

## 5. Comandos y herramientas
- `python scripts/harness/aws_guard.py --dry-run elasticbeanstalk update-environment ...` no aplica en
  PREPARING (sera DENIED): es esperado; el plan se valida en CANDIDATE_REVIEW.
- `python scripts/harness/evidence.py write --kind candidate --input .harness-runtime/payloads/candidate.json --runtime claude --session <id>`

## 6. Evidencia obligatoria
`candidate-*.json` completo: release_sha, account_id, region, environment, publish_run, images,
bundle, s3, application_version, environment_observed, lkg (con digests y `present`),
`smoke_plan` (checks de `environments/dev.yaml` + criterios de la tarea), `deployment_plan.commands`
(exactos), `rollback_plan.version_label` (= LKG). Blast radius y residuos posibles en `smoke_plan`/notas.

## 7. STOP
- Tarea clase C/D/E o que necesite option settings: `preparation_failed`.
- Cualquier dato del paquete sin evidencia observada.

## 8. Fuentes
- `docs/cicd/TPI_Contrato_CICD_AWS_v2.md` secciones 2, 5, 12.
- `docs/AWS_DEPLOYMENT_POLICY.md` seccion 3 (provisional); LL-04 residuos por fase.
