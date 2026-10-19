# Política de lifecycle de ECR en AWS DEV

Estado: propuesta aprobada como tarea `H3.2-ECR-LIFECYCLE` (clase C, infraestructura).
Ambiente: AWS DEV (`821656895812`, `us-east-2`), perfil `tpi-dev`.
Repositorios: `tpi-dev-app` y `tpi-dev-caddy`.

Este documento describe la política de retención de imágenes de Amazon ECR que conserva las
revisiones necesarias para el rollback version-only, el procedimiento de aplicación (que ejecuta
el humano, nunca un agente) y su reversa.

## Por qué 100

Cada release publica una imagen inmutable por SHA en `tpi-dev-app` y `tpi-dev-caddy`. La última
versión sana (LKG) y los candidatos de rollback deben permanecer disponibles aunque se acumulen
publicaciones fallidas o repetidas. La política anterior conservaba solo las 20 imágenes más
recientes (`imageCountMoreThan: 20`), lo que podía expirar imágenes que aún referenciaba el LKG.

Se eleva el tope a 100 (decisión del humano, 2026-10-19): conserva más, no menos, y mantiene el
LKG y los candidatos de rollback dentro de un margen amplio. El costo residual es solo
almacenamiento marginal. La regla 1 (limpieza de capas sin etiqueta a los 7 días) no cambia.

## Archivo de política

Un único archivo sirve a ambos repositorios: `deployment/ecr/lifecycle-policy.json`.

```json
{
  "rules": [
    {
      "rulePriority": 1,
      "description": "Expire untagged image layers after seven days.",
      "selection": {
        "tagStatus": "untagged",
        "countType": "sinceImagePushed",
        "countUnit": "days",
        "countNumber": 7
      },
      "action": { "type": "expire" }
    },
    {
      "rulePriority": 2,
      "description": "Retain the 100 most recent immutable DEV revisions.",
      "selection": {
        "tagStatus": "any",
        "countType": "imageCountMoreThan",
        "countNumber": 100
      },
      "action": { "type": "expire" }
    }
  ]
}
```

La prueba `tests/unit/test_ecr_lifecycle_policy.py` (sin AWS, corre en CI) lee este archivo y
falla si: no hay reglas, hay prioridades repetidas, alguna regla expira por antigüedad imágenes
con etiqueta, o el conteo de retención baja de 100. Así una reducción futura rompe CI en lugar de
pasar inadvertida.

## Procedimiento de aplicación (lo ejecuta el humano)

El Harness no aplica la política: `ecr put-lifecycle-policy` está denegado a los agentes. El
humano la aplica en AWS DEV para cada repositorio. Antes de confirmar, se genera una vista previa
para comprobar que no se expira ninguna imagen existente (hoy hay unas 20 por repositorio, por
debajo del tope de 100).

Para cada repositorio (`tpi-dev-app` y `tpi-dev-caddy`):

```bash
# 1. Vista previa (no aplica nada)
aws ecr start-lifecycle-policy-preview \
  --repository-name tpi-dev-app \
  --region us-east-2 \
  --profile tpi-dev

aws ecr get-lifecycle-policy-preview \
  --repository-name tpi-dev-app \
  --region us-east-2 \
  --profile tpi-dev

# 2. Aplicar la política versionada en git
aws ecr put-lifecycle-policy \
  --repository-name tpi-dev-app \
  --region us-east-2 \
  --profile tpi-dev \
  --lifecycle-policy-text file://deployment/ecr/lifecycle-policy.json

# 3. Verificar que quedó aplicada con el tope 100
aws ecr get-lifecycle-policy \
  --repository-name tpi-dev-app \
  --region us-east-2 \
  --profile tpi-dev
```

Repetir para `tpi-dev-caddy`. La vista previa debe mostrar que ninguna imagen existente resulta
afectada por la regla de retención (los repositorios tienen ~20 imágenes, por debajo de 100).

## Reversa

Reaplicar el JSON anterior desde git y confirmar la política:

```bash
# Recuperar la política anterior (imageCountMoreThan: 20) desde el historial
git show <sha-anterior>:deployment/ecr/lifecycle-policy.json > /tmp/lifecycle-policy-20.json

aws ecr put-lifecycle-policy \
  --repository-name tpi-dev-app \
  --region us-east-2 \
  --profile tpi-dev \
  --lifecycle-policy-text file:///tmp/lifecycle-policy-20.json
```

Repetir para `tpi-dev-caddy`. La reversa es segura: restablece el tope anterior sin borrar
imágenes de inmediato.

## Controles que se mantienen

La protección del LKG no depende solo de esta política. Siguen vigentes las comprobaciones de
digests en el release:

- Preflight (`aws-read-preflight`): verifica el LKG observado, el estado de su Application Version
  y que sus digests están presentes en ECR.
- Revisión del candidato (`tpi-release-readiness`): el check
  `lkg_all_digests_present_in_ecr` rechaza el candidato con causa `infra` si falta un digest del
  LKG en ECR.

Con el tope elevado a 100, esos checks dejan de ser el único freno frente a la expiración: las
imágenes requeridas por el LKG y por los candidatos de rollback permanecen en ECR con margen.

## Notas `keep-20` pendientes de actualizar (rutas protegidas del Harness)

Las siguientes referencias a `keep-20` viven en rutas protegidas (`agents/`), que un Developer no
edita; se listan aquí para actualizarlas en un mantenimiento aparte del Harness o por el humano:

- `agents/deployer/CONTEXT.md` — «ECR lifecycle keep-20 puede borrar imágenes del LKG: verificar
  todos sus digests antes del gate.»
- `agents/reviewer/CONTEXT.md` — «LKG = versión sana observada; sus digests deben existir en ECR
  (riesgo ECR lifecycle keep-20).»
- `agents/reviewer/skills/tpi-release-readiness/SKILL.md` — «Digests del LKG ausentes (ECR
  lifecycle keep-20): REJECTED `infra`.»

Tras esta tarea el riesgo cambia de `keep-20` a `keep-100`: conviene actualizar esas notas para
mantener la referencia al tope vigente.
