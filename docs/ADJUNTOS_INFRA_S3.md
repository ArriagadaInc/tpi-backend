# Adjuntos de notas: infraestructura S3 (paso 1)

Procedimiento del paso 1 de [`ADJUNTOS_COMENTARIOS_DISENO.md`](ADJUNTOS_COMENTARIOS_DISENO.md) (`CRM-ADJUNTOS-1-INFRA-S3`,
clase C). Lo aplica el humano con Claude interactivo; no es una tarea del Developer porque toca IAM.

Estado: **aplicado y verificado en AWS DEV el 2026-10-21** (`apply`: 12 comprobaciones en `OK`; `verify`: 7 en `PASA`; plan de GuardDuty
`12d0afd1193ea2e81987` en `ACTIVE`).

## Qué crea

| Recurso | Detalle | Archivo |
|---|---|---|
| Bucket `tpi-dev-adjuntos-821656895812-us-east-2` | Acceso público bloqueado, ACL deshabilitadas, cifrado SSE-S3, **sin versionado**, regla que aborta subidas multiparte incompletas, etiquetas del proyecto | creado por el script |
| Política del bucket | Solo TLS; **nadie lee `leads/*` si el objeto no tiene la etiqueta `GuardDutyMalwareScanStatus=NO_THREATS_FOUND`** (salvo el rol de GuardDuty); solo GuardDuty puede escribir o borrar esa etiqueta | `deployment/iam/tpi-dev-adjuntos-bucket-policy.json` |
| Rol `tpi-dev-guardduty-malware-s3-role` | Lo asume GuardDuty para leer, etiquetar y registrar los eventos del bucket | `…-guardduty-malware-s3-role-trust.json` y `…-role.json` |
| Permiso del rol `tpi-backoffice-dev-ec2-role` | `PutObject`, `GetObject` y `DeleteObject` sobre `leads/*`, y `GetObjectTagging` (solo lectura, para mostrar el estado del escaneo). Sin `ListBucket` y sin permisos para escribir o borrar etiquetas, para que la app no pueda falsificar el resultado del escaneo | `deployment/iam/tpi-backoffice-dev-adjuntos-s3.json` |
| Plan de GuardDuty Malware Protection for S3 | Protege el prefijo `leads/` y etiqueta cada objeto escaneado | creado por el script |

## Cómo se aplica

Todo se hace con `deployment/aws/adjuntos_s3_infra.py` y el perfil `tpi-dev` (sesión vigente: `aws login --profile tpi-dev --remote`).

```bash
python deployment/aws/adjuntos_s3_infra.py plan --profile tpi-dev
```

`plan` solo lee: compara lo que existe con lo esperado (`OK`, `FALTA` o `DIFIERE`) y no cambia nada.

```bash
python deployment/aws/adjuntos_s3_infra.py apply --profile tpi-dev --confirmar "CREAR INFRA ADJUNTOS DEV"
```

`apply` crea o corrige lo que falte, en este orden: bucket y su configuración, rol de GuardDuty y sus permisos, permiso de la app,
política del bucket, plan de GuardDuty y espera a que quede `ACTIVE`. Se puede repetir tras un fallo. Sin la frase exacta no
cambia nada.

```bash
python deployment/aws/adjuntos_s3_infra.py verify --profile tpi-dev
```

`verify` es la prueba de extremo a extremo (tarda unos minutos y deja el bucket sin archivos de prueba):

1. un objeto recién subido y sin escanear **no se puede leer**;
2. un archivo limpio queda `NO_THREATS_FOUND` y entonces **sí se puede leer**;
3. el archivo de prueba de antivirus EICAR queda `THREATS_FOUND` y **no se puede leer**;
4. **no se puede falsificar** la etiqueta, ni con `PutObjectTagging` ni subiendo el objeto con la etiqueta;
5. el permiso de la app cubre `leads/*` y nada más (se comprueba con el simulador de IAM).

El resultado del punto 1 puede salir `INCONCLUSO` si el escaneo termina antes de la lectura; no cuenta como falla.

## Retroceso

```bash
python deployment/aws/adjuntos_s3_infra.py rollback --profile tpi-dev --confirmar "ELIMINAR INFRA ADJUNTOS DEV"
```

Elimina el plan, el permiso de la app, la política y el bucket, y el rol de GuardDuty. **Se niega si el bucket tiene adjuntos
reales** (solo ignora los archivos de prueba de `verify`); en ese caso hay que decidir qué hacer con ellos antes de continuar.

## Cosas a vigilar

- **GuardDuty y su detector.** En `us-east-2` GuardDuty no estaba activado y el plan se creó igual, sin detector. Si en otro entorno lo
  exigiera, el script se detiene con un mensaje claro y **no lo activa solo**: activarlo tiene costo y es decisión del humano.
- **Costo.** GuardDuty cobra por GB escaneado (unos US$0,09 en us-east-1 desde febrero de 2025) y un cargo pequeño por objeto evaluado;
  la tarifa por objeto en esta región se confirma antes de habilitar la función. S3 cobra aparte las etiquetas.
- **Sin `s3:ListBucket`, S3 responde 403** tanto a un objeto inexistente como a uno denegado. Es esperado.
- **El rol de la instancia lo gestiona Elastic Beanstalk.** El permiso de la app es una política en línea; los permisos existentes
  del rol (SNS, secretos, ECR) no se tocan. Si se recrea el entorno, hay que volver a aplicar `apply`.
- **Confianza del rol de GuardDuty sin condiciones.** Sigue el patrón documentado por AWS; endurecerla con `aws:SourceAccount`
  queda como mejora si AWS confirma que el servicio la soporta.
