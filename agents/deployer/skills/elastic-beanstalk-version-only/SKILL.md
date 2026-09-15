---
name: elastic-beanstalk-version-only
role: deployer
load_when: "PREPARING_DEPLOYMENT (STAGING) y DEPLOYING (CUTOVER)"
sources: [release_contract_v2, aws_lessons_extracts, handoff_h33, aws_policy]
---

# elastic-beanstalk-version-only

## 1. Cuando se carga
STAGING en PREPARING_DEPLOYMENT (sin mutar runtime) y CUTOVER en DEPLOYING (tras Human Gate).

## 2. Puede
- STAGING: subir el bundle a key content-addressed nueva y crear la AV con `--no-process`.
- CUTOVER: un unico `update-environment` a la version aprobada; esperar estado.

## 3. No puede
- `--option-settings`, `--options-to-remove`, template/platform/tier.
- Sobrescribir keys, borrar/recrear AV, reutilizar labels, reintentar writes.
- `restart-app-server`, `rebuild-environment`, `swap-environment-cnames`, CodePipeline.

## 4. Precondiciones
- STAGING: bundle construido y verificado; preflight PASS.
- CUTOVER: estado DEPLOYING con aprobacion valida para el release SHA; preflight inmediato PASS.

## 5. Comandos y herramientas
STAGING:
- `python scripts/harness/aws_guard.py s3api put-object --bucket elasticbeanstalk-us-east-2-821656895812 --key tpi-backoffice/dev-releases/<label>/<bundle_sha256>.zip --body .harness-release/<label>.zip --checksum-algorithm SHA256 --checksum-sha256 <base64> --if-none-match "*" --content-type application/zip`
- `python scripts/harness/aws_guard.py s3api head-object --bucket <bucket> --key <key> --checksum-mode ENABLED`
- `python scripts/harness/aws_guard.py elasticbeanstalk create-application-version --application-name tpi-backoffice --version-label <label> --source-bundle S3Bucket=<bucket>,S3Key=<key> --no-process --no-auto-create-application`
- Si la key o la AV ya existen: verificar checksum/SourceBundle; si coinciden, reutilizar; si no, STOP.
CUTOVER:
- `python scripts/harness/aws_guard.py elasticbeanstalk update-environment --environment-name tpi-backoffice-dev-green --version-label <aprobada>`
- Espera acotada: `describe-environments` cada 30 s, maximo 30 min; `describe-events --max-records 20`.

## 6. Evidencia obligatoria
- STAGING (en candidate): s3 bucket/key/checksum_sha256/version_id, application_version label/status.
- CUTOVER (`deployment-*.json`): approved_commit, deployed_commit, application_version, environment,
  account_id, region, update_accepted, result, final_state, runtime_identity, started/finished,
  warnings, failure_class.

## 7. STOP
- Key existente con otro checksum o AV existente con otro SourceBundle o FAILED.
- `update-environment` rechazado: `deploy_failed` con `update_accepted: false` (NO rollback).
- Environment degradado o VersionLabel distinta tras espera: `deploy_failed` con `failure_class: infrastructure`.
- AccessDenied: STOP (evidencia automatica del guard).

## 8. Fuentes
- `docs/cicd/TPI_Contrato_CICD_AWS_v2.md` secciones 3 (pasos 3-8), 4, 14.
- `docs/cicd/LECCIONES_DEPLOY_AWS_H3_2_H3_3.md` LL-03 a LL-07; `docs/BITACORA.md` 2026-09-12.
