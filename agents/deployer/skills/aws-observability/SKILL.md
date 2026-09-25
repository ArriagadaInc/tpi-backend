---
name: aws-observability
role: deployer
load_when: "DEPLOYING (espera), VERIFYING y ROLLING_BACK"
sources: [release_contract_v2, aws_lessons, aws_lessons_extracts, release_contract_v1_extract, aws_policy]
---

# aws-observability

## 1. Cuando se carga
Despues de un `update-environment` aceptado (cutover o rollback) y en VERIFYING.

## 2. Puede
- Observar estado, eventos EB, identidad de runtime por cadena y conteos de patrones en logs.

## 3. No puede
- Volcar lineas de logs, valores del environment, URLs prefirmadas o `PhysicalResourceId`.
- Ocultar fallos de recoleccion (`|| true`): si no hay evidencia, fallar.

## 4. Precondiciones
- Estado DEPLOYING/VERIFYING/ROLLING_BACK; runtime Claude Code.

## 5. Comandos y herramientas
- `python scripts/harness/aws_guard.py elasticbeanstalk describe-environments --application-name tpi-backoffice --environment-names tpi-backoffice-dev-green --no-include-deleted`
- `python scripts/harness/aws_guard.py elasticbeanstalk describe-events --application-name tpi-backoffice --environment-name tpi-backoffice-dev-green --max-records 20`
- Cadena de identidad: VersionLabel == aprobada -> `describe-application-versions` SourceBundle == key
  aprobada -> `s3api head-object --checksum-mode ENABLED` ChecksumSHA256 == bundle -> digests del bundle == aprobados.
- Conteo PII/secretos: `python scripts/harness/aws_guard.py logs filter-log-events --log-group-name /aws/elasticbeanstalk/tpi-backoffice-dev-green/<stream> --filter-pattern "<patron>" --start-time <ms> --query "length(events)"`
  (v1.1: `--query` debe ser exactamente `length(events)`; cualquier otra proyeccion, p. ej.
  `events[].timestamp`, se deniega. Nunca se leen lineas).
- Clasificacion de conteos (v1.1, `harness/policies.yaml` `observability.log_indicators`):
  `python scripts/harness/log_scan.py classify --counts '{"Authorization": 0, "hash": 1}'`
  - **Fuertes** (Authorization, Bearer, password, cookie, raw_payload, secret, token; y todo
    patron no declarado): cualquier coincidencia bloquea `verified`. Nunca se degradan.
  - **Debiles** (`hash`, p. ej. `cert_hash` de Caddy/ACME): no equivalen a un secreto, pero
    cada coincidencia exige clasificacion **humana** (el humano inspecciona la linea; el
    Deployer no) registrada en `pii_log_scan.false_positives` con `classified_by: human`.

## 6. Evidencia obligatoria
- `runtime_identity` con los cuatro booleanos; `final_state`; eventos relevantes resumidos (sin
  secretos); `pii_log_scan` con `matches`, `raw_pattern_hits` (conteos), `strong_matches`,
  `weak_matches`, `classification_required` y, si hubo debiles, `false_positives` humanos.
  El guard `verification_passed` recalcula la clasificacion desde los conteos.

## 7. STOP
- Evento con AccessDenied, abort o rollback inesperado de EB.
- No se puede recopilar evidencia: fallo de observabilidad (`failure_class: observability`).

## 8. Fuentes
- `docs/cicd/TPI_Contrato_CICD_AWS_v2.md` principio 2 y seccion 12.
- `docs/AWS_DEPLOYMENT_BEST_PRACTICES.md` principio 3; LL-07, LL-14; extracto v1 puntos 3-5.
