---
name: aws-read-preflight
role: deployer
load_when: "PREPARING_DEPLOYMENT (inicio) y DEPLOYING (antes de update-environment)"
sources: [release_contract_v2, aws_policy, aws_lessons_extracts, aws_rules, mcp_setup]
---

# aws-read-preflight

## 1. Cuando se carga
Antes de cualquier escritura AWS preparatoria y otra vez inmediatamente antes del cutover.

## 2. Puede
- Lecturas allowlisted via `aws_guard.py`: identidad, environment, application versions, eventos,
  imagenes ECR, head-object de releases, estado del pipeline.
- Consultar AWS MCP read-only para parametros de CLI.

## 3. No puede
- Escrituras; `describe-configuration-settings`; leer secretos; imprimir `PhysicalResourceId` o URLs.
- Elegir el LKG por timestamp o desde documentos.

## 4. Precondiciones
- Runtime Claude Code; `environments/dev.yaml` valido; init PASS.

## 5. Comandos y herramientas
- `python scripts/harness/aws_guard.py sts get-caller-identity`
- `python scripts/harness/aws_guard.py elasticbeanstalk describe-environments --application-name tpi-backoffice --environment-names tpi-backoffice-dev-green --no-include-deleted`
- `python scripts/harness/aws_guard.py elasticbeanstalk describe-application-versions --application-name tpi-backoffice --version-labels <lkg>`
- Por cada digest del LKG (leidos del compose del bundle del LKG o de su evidencia de release):
  `python scripts/harness/aws_guard.py ecr describe-images --repository-name <repo> --image-ids imageDigest=<digest>`
- `python scripts/harness/aws_guard.py codepipeline get-pipeline-state --name tpi-backoffice-dev-promotion` (Promote debe seguir deshabilitado)

## 6. Evidencia obligatoria
En el candidate (`environment_observed`, `lkg`): cuenta, region, VersionLabel observada,
Status/Health/HealthStatus, LKG = version observada, estado de su AV, lista de digests con `present`.

## 7. STOP
- Cuenta distinta de `821656895812` o region distinta de `us-east-2`.
- Environment no Ready/Green/Ok o con update en curso.
- AV del LKG ausente/FAILED o cualquier digest del LKG ausente en ECR (STOP antes del Human Gate).
- AccessDenied (aws_guard registra evidencia `failure`): `preparation_failed`.
- Promote de CodePipeline habilitado inesperadamente: STOP y auditar.

## 8. Fuentes
- `docs/cicd/TPI_Contrato_CICD_AWS_v2.md` secciones 3 (paso 6), 5, 14.
- `docs/AWS_DEPLOYMENT_POLICY.md` seccion 4 (provisional); `docs/cicd/LECCIONES_DEPLOY_AWS_H3_2_H3_3.md` LL-02, LL-17.
