---
name: tpi-deployment-safety-review
role: reviewer
load_when: "CANDIDATE_REVIEW"
sources: [release_contract_v2, aws_policy, aws_lessons_extracts, release_contract_v1_extract, aws_lessons]
---

# tpi-deployment-safety-review

## 1. Cuando se carga
CANDIDATE_REVIEW, sobre `deployment_plan` y `rollback_plan` del candidate.

## 2. Puede
- Validar el plan contra `harness/policies.yaml` y el contrato.
- Verificar el plan por inspeccion de sus comandos, las politicas y el contrato; documentar las fuentes de cada check.
- En CANDIDATE_REVIEW no invocar `update-environment`, tampoco con `--dry-run`: el modo candidate_read no lo permite.
- Para `plan_commands_in_state_allowlist`, comprobar los permisos del Deployer en DEPLOYING y las condiciones de rollback correspondientes; no confundirlos con los permisos actuales del Reviewer.
- Mantener todos los checks obligatorios. No marcar PASS si la inspeccion no permite demostrarlo; declarar que no se ejecuto dry-run.

## 3. No puede
- Ejecutar comandos del plan ni modificarlo.

## 4. Precondiciones
- `candidate-*.json` con `deployment_plan.commands`, `rollback_plan`, `smoke_plan`.

## 5. Comandos y herramientas
- Lectura de `harness/policies.yaml` (`aws.modes.cutover`, `rollback_authorization`).

## 6. Evidencia obligatoria
Checks (PASS/FAIL):
- `cutover_is_version_label_only` (sin `--option-settings`, template, platform, tier).
- `plan_commands_in_state_allowlist`.
- `single_promotion_no_retries`.
- `rollback_version_only_to_named_lkg_single_attempt`.
- `no_iam_dns_secrets_migrations_in_plan`.
- `outputs_redacted_safe_to_log`.
- `residue_classification_by_phase` (S3 / AV / environment en transicion).
- `functional_failure_does_not_trigger_rollback`.

## 7. STOP
- El plan necesita option settings o cualquier cambio clase C/D/E: REJECTED `infra`.
- Rollback automatico no condicionado o por timestamp: REJECTED `artifact`.

## 8. Fuentes
- `docs/cicd/TPI_Contrato_CICD_AWS_v2.md` secciones 4, 13, 14.
- `docs/AWS_DEPLOYMENT_POLICY.md` seccion 4 (provisional).
- `docs/cicd/LECCIONES_DEPLOY_AWS_H3_2_H3_3.md` LL-04, LL-06; `docs/cicd/CONTRATO_CICD_AWS_V1_EXTRACTO.md` punto 7.
