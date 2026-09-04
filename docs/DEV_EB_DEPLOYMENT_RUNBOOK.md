# Runbook de promoción controlada a Elastic Beanstalk DEV

Estado: preparado, no aprovisionado ni ejecutado
Ambiente: AWS DEV (`821656895812`, `us-east-2`)
Última validación física del baseline: 2026-09-04
Fuente: preflight EB, candidato ECR congelado y contratos versionados

## Baseline

| Elemento | Valor |
| --- | --- |
| Aplicación | `tpi-backoffice` |
| Environment | `tpi-backoffice-dev-green` |
| Estado previo | `h2-5d-ecr-47fa0c9`, `Ready / Green / Ok` |
| Rollback | `h2-5d-ecr-47fa0c9` |
| Candidato | `h3-3-crm-web-28cf009-r1` |
| Runtime SHA | `28cf009137ada707540d9ee7eba01dc45a9a260e` |
| Artifact GitHub | Run `33824477381`, ID `9919549285` |

La arquitectura y límites de confianza están en
`docs/DEV_EB_CODEPIPELINE_ARCHITECTURE.md`.

## Aprovisionamiento pendiente

Ejecutar desde una sesión administrativa controlada y validada en la cuenta
`821656895812`. Estos comandos son instrucciones; no han sido ejecutados por
este PR.

1. Crear los buckets dedicados de release y artifact store. Activar versionado
   en el bucket de release y cifrado/bloqueo público en ambos:

```bash
aws s3api create-bucket --region us-east-2 \
  --bucket tpi-dev-release-artifacts-821656895812-us-east-2 \
  --create-bucket-configuration LocationConstraint=us-east-2
aws s3api put-bucket-versioning \
  --bucket tpi-dev-release-artifacts-821656895812-us-east-2 \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption \
  --bucket tpi-dev-release-artifacts-821656895812-us-east-2 \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-public-access-block \
  --bucket tpi-dev-release-artifacts-821656895812-us-east-2 \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api create-bucket --region us-east-2 \
  --bucket tpi-dev-codepipeline-artifacts-821656895812-us-east-2 \
  --create-bucket-configuration LocationConstraint=us-east-2
aws s3api put-bucket-encryption \
  --bucket tpi-dev-codepipeline-artifacts-821656895812-us-east-2 \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-public-access-block \
  --bucket tpi-dev-codepipeline-artifacts-821656895812-us-east-2 \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

2. Publicar el tooling privilegiado desde el commit aprobado usando un operador
   AWS, nunca el rol GitHub. Fallar si los hashes no coinciden:

```bash
test "$(sha256sum scripts/release/verify_frozen_candidate.sh | cut -d' ' -f1)" = \
  a59144ff469e56231addb7c46ccf3fa7d456ff9487c7387089eec9137a045791
test "$(sha256sum deployment/aws/promote_eb_candidate.py | cut -d' ' -f1)" = \
  fbbbf2fdc3025612627945a312144e4d8972657b1f8240bd142a6ed13b552c86
aws s3api put-object \
  --bucket tpi-dev-release-artifacts-821656895812-us-east-2 \
  --key trusted-tooling/v1/verify_frozen_candidate.sh \
  --body scripts/release/verify_frozen_candidate.sh
aws s3api put-object \
  --bucket tpi-dev-release-artifacts-821656895812-us-east-2 \
  --key trusted-tooling/v1/promote_eb_candidate.py \
  --body deployment/aws/promote_eb_candidate.py
```

3. Crear el service role de CodePipeline y adjuntar exclusivamente la policy
   versionada:

```bash
aws iam create-role --role-name tpi-codepipeline-dev-eb-role \
  --assume-role-policy-document \
  file://deployment/iam/tpi-codepipeline-dev-eb-role-trust.json
aws iam put-role-policy --role-name tpi-codepipeline-dev-eb-role \
  --policy-name TpiCodePipelineDevElasticBeanstalk \
  --policy-document file://deployment/iam/tpi-codepipeline-dev-eb.json
```

4. Crear el rol OIDC de orquestación GitHub:

```bash
aws iam create-role --role-name tpi-github-actions-dev-release-role \
  --assume-role-policy-document \
  file://deployment/iam/tpi-github-actions-dev-release-role-trust.json
aws iam put-role-policy --role-name tpi-github-actions-dev-release-role \
  --policy-name TpiGithubDevReleaseOrchestration \
  --policy-document file://deployment/iam/tpi-github-actions-dev-release.json
```

5. Crear el pipeline V2 sin ejecutarlo:

```bash
aws codepipeline create-pipeline --region us-east-2 \
  --cli-input-json file://deployment/aws/tpi-dev-eb-pipeline.json
```

6. Verificar trust, policies, buckets, objetos de tooling y pipeline mediante `get-role`,
   `get-role-policy`, `get-bucket-versioning`, `get-public-access-block` y
   `get-pipeline`. Comparar además los SHA-256 del tooling descargado. No iniciar
   promoción en esta fase.

7. Tras validar el nuevo flujo, retirar el rol físico histórico
   `tpi-github-actions-dev-eb-deploy-role`. No reutilizarlo ni ampliarlo.

## Preflight de promoción

Ejecutar primero el workflow con `execute_promotion=false`. Debe:

1. Verificar el artifact GitHub y sus cuatro anclajes inmutables.
2. Asumir únicamente `tpi-github-actions-dev-eb-role`.
3. Confirmar cuenta, aplicación y environment.
4. Aceptar solo el rollback o candidato en `Ready / Green / Ok`.
5. Confirmar rollback utilizable.
6. Confirmar candidato ausente o coincidente con el source legacy aprobado.
7. Finalizar sin objetos S3 nuevos ni ejecución de CodePipeline.

## Promoción autorizada

Solo tras aprobar el preflight:

1. Ejecutar una vez con `execute_promotion=true`.
2. GitHub publica bundle, manifest y source data-only en el bucket TPI.
3. GitHub inicia únicamente `tpi-backoffice-dev-promotion`, fijando solo el
   `VersionId`; la clave source no puede sobrescribirse.
4. CodePipeline descarga el tooling desde el prefijo protegido, verifica ambos
   hashes y recién entonces ejecuta la validación/promoción.
5. CodePipeline valida el objeto, crea o reutiliza la versión exacta y conserva
   `h2-5d-ecr-47fa0c9`.
6. Si procede, actualiza solo `tpi-backoffice-dev-green`.
7. Exige `h3-3-crm-web-28cf009-r1`, `Ready / Green / Ok`.
8. GitHub recoge action executions, estado EB y eventos con el rol read-only.

## Rollback

El rollback requiere autorización separada. Actualizar únicamente
`tpi-backoffice-dev-green` a `h2-5d-ecr-47fa0c9`, esperar
`Ready / Green / Ok` y conservar artefactos y application versions para
auditoría. No modificar variables, DNS, RDS, roles del environment ni buckets.

## Matriz de fallos

| Fase | Efecto posible | Acción |
| --- | --- | --- |
| Verificación/preflight | Sin escrituras | Corregir evidencia, no promover |
| Publicación | Objetos versionados en bucket TPI | Conservar y diagnosticar |
| Pipeline antes de update | Puede existir Application Version | Reanudar solo si source coincide |
| Pipeline después de update | Environment puede estar cambiando | Recoger eventos; no reintentar ni hacer rollback automático |

No borrar `h3-3-crm-web-28cf009-r1` para reanudar. Una discrepancia de source
requiere detenerse, no sobrescribir ni eliminar automáticamente.
