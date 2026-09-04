# Runbook de deployment controlado en Elastic Beanstalk DEV

Estado: preparado, no ejecutado
Ambiente: AWS DEV (`us-east-2`)
Última validación física del baseline: 2026-09-04
Fuente: preflight EB, artifact ECR publicado y políticas IAM versionadas

## Alcance

Este runbook describe el deployment controlado del candidato congelado H3.3.
El workflow asociado es manual, solo puede ejecutarse desde `main` y no modifica
la configuración del environment. Su única actualización de runtime es cambiar
`VersionLabel` en `tpi-backoffice-dev-green`.

El rol de preflight `tpi-github-actions-dev-eb-role` permanece read-only. El
deployment usa el rol separado `tpi-github-actions-dev-eb-deploy-role`.

## Baseline aprobado

| Elemento | Valor |
| --- | --- |
| Cuenta | `821656895812` |
| Región | `us-east-2` |
| Aplicación | `tpi-backoffice` |
| Environment | `tpi-backoffice-dev-green` |
| CNAME EB | `tpi-backoffice-dev-ecr.us-east-2.elasticbeanstalk.com` |
| Versión actual | `h2-5d-ecr-47fa0c9` |
| Rollback | `h2-5d-ecr-47fa0c9` (versión saludable observada) |
| Runtime SHA | `28cf009137ada707540d9ee7eba01dc45a9a260e` |
| Nueva versión EB | `h3-3-crm-web-28cf009-r1` |
| Artifact ECR | Run `33824477381`, artifact `9919549285` |

El artifact contiene `tpi-dev-ecr-28cf009.zip` y su manifest. El workflow
verifica el SHA-256 del ZIP, el runtime SHA, ambos digests ECR y que el ZIP
contenga únicamente `docker-compose.yml` antes de asumir AWS.

## IAM

Trust OIDC del rol de deployment:

- `aud`: `sts.amazonaws.com`.
- `sub`: repositorio exacto y `refs/heads/main`.
- Sin wildcard y sin autorización de `pull_request`.

Permisos versionados:

- `elasticbeanstalk:DescribeApplications`.
- `elasticbeanstalk:DescribeEnvironments`.
- `elasticbeanstalk:DescribeApplicationVersions`.
- `elasticbeanstalk:DescribeEvents`.
- `elasticbeanstalk:CreateApplicationVersion` sobre `tpi-backoffice`.
- `elasticbeanstalk:UpdateEnvironment` únicamente sobre `tpi-backoffice-dev-green`.
- `s3:PutObject`, `s3:GetObject` y `s3:GetObjectVersion` únicamente bajo
  `tpi-backoffice/dev-releases/*` del bucket EB existente. `CreateApplicationVersion`
  necesita que el principal de deployment pueda volver a leer el source bundle
  después de subirlo.
No se conceden `iam:PassRole`, acciones IAM, cambios DNS, cambios RDS,
`UpdateConfigurationTemplate`, `CreateBucket`, `DeleteBucket`, permisos de
administración del bucket, `ListAllMyBuckets` ni permisos para modificar variables
del environment.

## Flujo controlado

1. Ejecutar el workflow `Deploy frozen DEV candidate to Elastic Beanstalk` desde `main`.
2. Verificar cuenta, región, aplicación, environment, versión actual y estado `Ready / Green / Ok`.
3. Verificar que la versión actualmente desplegada `h2-5d-ecr-47fa0c9` existe exactamente una vez, no está en estado `FAILED` y tiene `SourceBundle` informado. Esa versión saludable observada es el rollback del release; no se requieren eventos históricos para demostrarlo.
4. Subir el ZIP al prefijo de release del bucket EB.
5. Crear `h3-3-crm-web-28cf009-r1` apuntando al objeto exacto, sin solicitar
   preprocesamiento a Elastic Beanstalk. Para source bundles S3, `Process` es opcional;
   el pipeline ya valida localmente el ZIP, Docker Compose y los digests inmutables.
6. Aceptar `UNPROCESSED` o `PROCESSED`; esperar mientras el estado sea `PROCESSING`
   y abortar ante `FAILED`, estado desconocido o timeout. `UNPROCESSED` indica que
   Elastic Beanstalk validará la configuración durante el deployment.
7. Verificar `VersionLabel`, `SourceBundle.S3Bucket`, `SourceBundle.S3Key` y
   `Status != FAILED`, además de conservar el rollback antes de actualizar el environment.
8. Ejecutar `UpdateEnvironment` solo con `--version-label`, sin opciones de configuración.
9. Esperar `Ready / Green / Ok` y confirmar la nueva versión.
10. Revisar los últimos eventos de Elastic Beanstalk, incluso si falla la espera posterior al update.

La validación del artifact y el preflight terminan antes de cualquier escritura.
Después de `PutObject` y `CreateApplicationVersion` puede fallar la validación
posterior, quedando un objeto S3 y/o una application version sin tocar todavía el
environment. Si falla `UpdateEnvironment` o la espera de estabilidad, el
environment puede haber iniciado un cambio y debe verificarse antes de ejecutar
rollback; los eventos se recopilan para ese diagnóstico.

Resumen de efectos:

| Fase | Resultado ante fallo |
| --- | --- |
| Validación del artifact/preflight | Cero escrituras |
| Registro y validación de application version | Puede quedar objeto S3/application version; environment intacto |
| `UpdateEnvironment` o espera posterior | Puede haber iniciado un deployment; revisar eventos y ejecutar rollback si corresponde |

## Rollback

El rollback se realiza actualizando exclusivamente el mismo environment a la
versión saludable observada inmediatamente antes del deployment,
`h2-5d-ecr-47fa0c9`, usando el rol de
deployment o un operador autorizado. Luego se espera `Ready / Green / Ok` y se
confirma `VersionLabel`.

No modificar variables, CNAME, configuración, RDS, IAM ni el bucket durante el
rollback. La application version nueva y el objeto S3 se conservan para
auditoría hasta aplicar la política de retención aprobada.

## No ejecutar durante este PR

- No ejecutar el workflow de deployment.
- No ejecutar migraciones RDS.
- No regenerar imágenes ni bundle.
- No rebasear PR #14.
- No hacer smoke funcional ni mergear PR #14.
