# Runbook de promoción controlada a Elastic Beanstalk DEV

Estado: aprovisionado; promoción H3.3 fallida antes de cambiar el environment
Ambiente: AWS DEV (`821656895812`, `us-east-2`)
Última validación física del baseline: 2026-09-07
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

## Evidencia de la promoción detenida

| Elemento | Evidencia |
| --- | --- |
| GitHub Actions | Run `34147747678` |
| CodePipeline | `fbd91cee-1fe7-4535-8025-cd9f98a58fc9` |
| Source | `Succeeded` |
| Promote | `Failed` |
| Causa original | `cloudformation:GetTemplate` denegado al service role de CodePipeline |
| Stack físico | `awseb-e-sd5gmkxr5r-stack` |
| Stack status / role | `UPDATE_COMPLETE`; `RoleARN = null` |
| Tipos del stack | ASG, Launch Template, EIP, WaitCondition y WaitConditionHandle |
| ASG | `awseb-e-sd5gmkxr5r-stack-AWSEBAutoScalingGroup-MkPjH46TJf2L`; tag del stack exacto |
| ASG service-linked role | `AWSServiceRoleForAutoScaling` |
| Launch Template | `lt-0c69191d0013fa448`, versión 1, sin tags CloudFormation |
| Estado EB posterior | `h2-5d-ecr-47fa0c9`, sin cambio |

El source versionado, el tooling confiable y el artifact congelado fueron
validados antes del fallo. No se debe reintentar hasta aplicar y verificar la
policy caller-side versionada. El error original se conserva aunque la
recolección posterior de diagnósticos falle.

`UpdateEnvironment` no es una llamada aislada: Elastic Beanstalk usa permisos
del caller para orquestar CloudFormation y recursos subyacentes. La inspección
física debe ocurrir antes de revisar o aplicar IAM. En este environment,
`RoleARN = null`, por lo que CloudFormation utiliza credenciales derivadas del
caller para actualizar el ASG y el Launch Template. El EIP solo se inspecciona;
la promoción no autoriza modificarlo. El ASG usa el service-linked role de
Auto Scaling para lanzar instancias, por lo que el service role de CodePipeline
no recibe `ec2:RunInstances`. El Launch Template se limita a su ARN físico exacto
y a crear/eliminar versiones; no se autoriza modificar su versión default. No se adjunta
`AdministratorAccess-AWSElasticBeanstalk` ni se agregan permisos por sucesivos
reintentos de deployment.

## Contrato de aprovisionamiento aplicado

El plano fue aprovisionado desde una sesión administrativa controlada en la
cuenta `821656895812`. Los comandos siguientes se conservan como contrato
reproducible; no deben repetirse sobre recursos existentes sin un preflight y
una autorización independientes.

Antes de aplicar una revisión de la policy del service role, capturar el
inventario físico sin parámetros ni valores de configuración:

```bash
bash scripts/release/inspect_dev_eb_control_plane_readonly.sh
```

La inspección falla si la cuenta, application, environment o stack no coinciden
con el contrato. Solo usa STS, `DescribeEnvironments`, `DescribeStacks`,
`ListStackResources` y `GetTemplate`. Del inventario imprime exclusivamente
`LogicalId`, `ResourceType` y `ResourceStatus`; nunca `PhysicalResourceId`, que
puede contener URLs prefirmadas. De la plantilla imprime solo los tipos. La
salida física debe conservarse antes de definir el contrato IAM y antes de
autorizar otra promoción.

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
  4ba84447a948238ff877fa95e60e52f9b52e0b9bc2bad3e80fd236a03a9675f9
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

5. Comprobar de forma fail-closed que el source del candidato está ausente y
   ejecutar el bootstrap seguro:

```bash
bash scripts/release/bootstrap_dev_codepipeline.sh
```

   `CreatePipeline genera una ejecución automática`. El script exige que
   `candidate-data.zip` no exista, crea el pipeline, deshabilita inmediatamente
   la transición inbound de `Promote` con la razón
   `Promotion not authorized - provisioning validation` y conserva evidencia de
   la ejecución automática. El bootstrap debe fallar en `Source` con estado
   `Failed`; la evidencia autoritativa es exactamente una action execution
   `Source / ApprovedReleaseSource / Failed`, la ausencia posterior del source
   exacto y cero action executions en `Promote`. El mensaje de error de AWS es evidencia
   diagnóstica opcional y puede estar ausente.
   Cualquier error distinto de `404/NotFound` al comprobar S3 aborta antes de
   crear el pipeline; si el objeto existe, no se elimina automáticamente.

6. Conservar como evidencia el ID, trigger, estado y action executions emitidos
   por el script. El error o resumen externo de `Source`, cuando AWS lo entrega,
   se conserva solo como diagnóstico. Para revalidar de forma read-only e
   idempotente un pipeline ya creado, ejecutar:

```bash
bash scripts/release/validate_dev_codepipeline_bootstrap.sh \
  cb585cf4-ceec-4dd3-9482-6853f441a2ac
```

   El validador vuelve a comprobar el pipeline físico, la ejecución exacta, una
   sola action `Source / ApprovedReleaseSource / Failed`, el source S3 ausente,
   cero `Promote`, la transición inbound deshabilitada, el baseline EB y el
   candidato intacto. Verificar además trust, policies, buckets, objetos de
   tooling y pipeline mediante `get-role`, `get-role-policy`,
   `get-bucket-versioning`, `get-public-access-block`, `get-pipeline` y
   `get-pipeline-state`. Confirmar físicamente:

   - `pipelineType = V2` y `executionMode = QUEUED`;
   - bucket y key source exactos;
   - `AllowOverrideForS3ObjectKey = false` y `PollForSourceChanges = false`;
   - service role exacto;
   - transición inbound de `Promote` deshabilitada;
   - cero action executions en `Promote`;
   - EB continúa en `h2-5d-ecr-47fa0c9`, `Ready / Green / Ok`;
   - `h3-3-crm-web-28cf009-r1` permanece intacta.

   Comparar además los SHA-256 del tooling descargado. El fallo inicial de
   `Source` es el resultado seguro esperado del provisioning, no una promoción
   fallida. No habilitar `Promote` ni iniciar promoción en esta fase.

7. Tras aprovisionar y validar el pipeline, retirar o deshabilitar el rol físico
   histórico `tpi-github-actions-dev-eb-deploy-role` **antes** de la primera
   ejecución con `execute_promotion=true`. Confirmar que ya no constituye un
   trust path alternativo desde GitHub. No reutilizarlo ni ampliarlo.

8. Ejecutar `execute_promotion=false`, comprobar nuevamente EB en
   `h2-5d-ecr-47fa0c9`, `Ready / Green / Ok`, y detenerse. La transición inbound
   de `Promote` permanece deshabilitada hasta una autorización separada para la
   promoción H3.3.

## Preflight de promoción

Ejecutar primero el workflow con `execute_promotion=false`. Debe:

1. Verificar el artifact GitHub y sus cuatro anclajes inmutables.
2. Asumir únicamente `tpi-github-actions-dev-eb-role`.
3. Confirmar cuenta, aplicación y environment.
4. Aceptar solo el rollback o candidato en `Ready / Green / Ok`.
5. Confirmar rollback utilizable.
6. Confirmar candidato ausente o coincidente con el source legacy o aprobado exacto.
7. Finalizar sin objetos S3 nuevos ni ejecución de CodePipeline.

## Promoción autorizada

Solo tras aprobar el preflight:

1. Ejecutar una vez con `execute_promotion=true`.
2. GitHub publica únicamente el source data-only versionado en el bucket TPI.
3. GitHub inicia únicamente `tpi-backoffice-dev-promotion`, fijando solo el
   `VersionId`; la clave source no puede sobrescribirse.
4. CodePipeline comprueba `aws`, `python3`, `bash`, `jq`, `sha256sum`, `zipinfo`,
   `unzip`, `docker` y `docker compose`; no instala herramientas en runtime.
5. CodePipeline descarga el tooling desde el prefijo protegido, verifica ambos
   hashes y recién entonces ejecuta la validación/promoción.
6. Si la versión no existe, el promotor recalcula el hash del bundle verificado,
   lo materializa con checksum S3 bajo el objeto exacto de `approved-releases/`
   y comprueba el checksum almacenado antes de crear la Application Version.
7. Si la versión ya existe, solo acepta el source legacy exacto o el objeto
   aprobado exacto. Además descarga y calcula SHA-256 del legacy, o consulta y
   compara `ChecksumSHA256` del objeto aprobado, antes de permitir el update.
   Cualquier tercer source o contenido discrepante aborta.
8. CodePipeline conserva `h2-5d-ecr-47fa0c9`.
9. Si procede, actualiza solo `tpi-backoffice-dev-green`.
10. Exige `h3-3-crm-web-28cf009-r1`, `Ready / Green / Ok`.
11. GitHub recoge action executions, estado EB y eventos con el rol read-only.

La observación de CodePipeline tolera de forma acotada solamente
`PipelineExecutionNotFoundException` inmediatamente después de
`StartPipelineExecution`, porque el ID puede tardar en ser visible. Se realizan
como máximo seis reintentos con backoff de 5, 10, 15, 20, 25 y 30 segundos. Un
`NotFound` posterior a la primera observación válida aborta inmediatamente. Los
estados terminales negativos `Cancelled`, `Failed`, `Stopped` y `Superseded`
también abortan de forma explícita. Cualquier otro error AWS aborta; el polling
completo vence tras 90 observaciones y entrega el execution ID y el último
estado como diagnóstico.

## Rollback

El rollback requiere autorización separada. Actualizar únicamente
`tpi-backoffice-dev-green` a `h2-5d-ecr-47fa0c9`, esperar
`Ready / Green / Ok` y conservar artefactos y application versions para
auditoría. No modificar variables, DNS, RDS, roles del environment ni buckets.
El rollback no depende del rol histórico de GitHub: ante una emergencia se
ejecuta desde una sesión AWS administrativa controlada y auditada.

## Matriz de fallos

| Fase | Efecto posible | Acción |
| --- | --- | --- |
| Verificación/preflight | Sin escrituras | Corregir evidencia, no promover |
| Publicación | Objetos versionados en bucket TPI | Conservar y diagnosticar |
| Pipeline antes de update | Puede existir Application Version | Reanudar solo si source coincide |
| Pipeline después de update | Environment puede estar cambiando | Recoger eventos; no reintentar ni hacer rollback automático |

No borrar `h3-3-crm-web-28cf009-r1` para reanudar. Una discrepancia de source
requiere detenerse, no sobrescribir ni eliminar automáticamente.

## Recuperación cuando el publish falla por el escaneo de ECR

El workflow `publish-dev-ecr-images.yml` espera hasta `SCAN_TIMEOUT_MINUTES` minutos
(sondeando cada `SCAN_POLL_SECONDS` segundos) a que el escaneo de ECR de ambas imagenes
(`tpi-dev-app` y `tpi-dev-caddy`) termine en `COMPLETE`, y mantiene el gate fail-closed:
sin un `COMPLETE` con `CRITICAL=0` y `HIGH=0` en ambas imagenes no se arma el bundle ni
se sube el artefacto, y `IN_PROGRESS` nunca cuenta como exito. Un escaneo atascado mas de
20 minutos seguira fallando: la solucion no es esperar indefinidamente, es el
procedimiento de recuperacion.

Los tres mensajes de fallo se distinguen asi:

| Mensaje | Significado | Accion |
| --- | --- | --- |
| «no termino en el plazo ... NO hay hallazgos verificados» | El escaneo no llego a `COMPLETE` dentro del plazo (suele quedar en `IN_PROGRESS`). No se puede afirmar nada sobre la seguridad de la imagen. | Borrar y relanzar (abajo). |
| «termino en FAILED» o «termino en UNSUPPORTED_IMAGE» | ECR no pudo escanear la imagen; no hay un resultado utilizable. | Borrar y relanzar (abajo). |
| «Hallazgos HIGH o CRITICAL ... CRITICAL=... HIGH=...» | El escaneo termino y encontro hallazgos reales, con el detalle a continuacion. | Remediar la imagen (dependencias/base) y volver a publicar. |

Procedimiento de recuperacion (lo ejecuta el humano; los tags son inmutables):

1. Revisar el estado del escaneo de ambos digests:
   `aws ecr describe-image-scan-findings --repository-name <repo> --image-id imageDigest=<digest> --query 'imageScanStatus.status' --output text`.
2. Borrar las dos imagenes del release (`tpi-dev-app` y `tpi-dev-caddy`). Los tags son
   inmutables, por lo que solo el humano puede borrarlas; sin borrarlas, relanzar el
   workflow no vuelve a escanearlas (el tag ya existe y ECR no reescanea por push).
3. Relanzar el workflow con el mismo SHA (`workflow_dispatch` con el `source_sha` original).

### El escaneo nunca empieza: la imagen publicada es un indice OCI

Sintoma: `describe-image-scan-findings` responde `ScanNotFoundException` para el digest y
`aws ecr start-image-scan` responde `UnsupportedImageTypeException` («An artifact with media type
'application/vnd.oci.image.index.v1+json' cannot be scanned»). El gate del workflow vence a los 20
minutos con el mensaje «no termino en el plazo».

Causa (2026-10-23): `ubuntu-latest` paso a `ubuntu-26.04`; ahi `docker build` + `docker push` suben a
ECR un indice OCI con un manifiesto de atestacion, y ECR no escanea indices. En `ubuntu-24.04` se sube
un manifiesto Docker v2 (`application/vnd.docker.distribution.manifest.v2+json`), que si se escanea.

Solucion: el workflow fija todos sus jobs en `ubuntu-24.04` y una prueba
(`tests/security/test_ecr_scan_wait_workflow.py`) lo vigila. Comprobacion tras publicar:
`aws ecr describe-images --repository-name <repo> --image-ids imageTag=<sha> --query 'imageDetails[0].imageManifestMediaType' --output text`
debe mostrar `application/vnd.docker.distribution.manifest.v2+json`, no un `...index...`.

Si un publish ya subio indices, borrar las dos imagenes del release (procedimiento anterior) y
relanzar el workflow con el mismo SHA una vez corregido (el workflow se toma de `main`). Los
manifiestos hijos sin tag que deja el indice son inertes. Si con `ubuntu-24.04` siguiera apareciendo
un indice, agregar `--provenance=false --sbom=false` a los `docker build` del paso de publicacion.
