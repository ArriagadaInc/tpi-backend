---
name: rollback-version-only
role: deployer
load_when: "DEPLOY_FAILED o VERIFY_FAILED con degradacion de infraestructura; ROLLING_BACK"
sources: [release_contract_v2, aws_lessons_extracts, release_contract_v1_extract, aws_policy]
---

# rollback-version-only

## 1. Cuando se carga
Solo cuando la autorizacion condicionada del Human Gate puede aplicar.

## 2. Puede
- Un unico `update-environment --version-label <LKG aprobado>` en ROLLING_BACK.

## 3. No puede
- Rollback si UpdateEnvironment fue rechazado, por defecto funcional, por timestamp, con option
  settings, hacia otra version, o un segundo intento.

## 4. Precondiciones (las 7, todas verificadas con evidencia en el precheck)
1. `update-environment` fue aceptado.
2. Environment degradado, inconsistente o sin el estado esperado.
3. AV del LKG utilizable (existe, no FAILED, con SourceBundle).
4. Todos los digests del LKG presentes en ECR.
5. El rollback no requiere option settings.
6. No es un defecto puramente funcional.
7. No hubo rollback previo.

## 5. Comandos y herramientas
- Precheck: `aws_guard.py elasticbeanstalk describe-application-versions ...`; `ecr describe-images ...` por digest.
- `python scripts/harness/evidence.py write --kind rollback --input <precheck.json> ...` con `phase: precheck`.
- `python scripts/harness/transition.py start_rollback --evidence <ruta> --runtime claude --session <id>`
- `python scripts/harness/aws_guard.py elasticbeanstalk update-environment --environment-name tpi-backoffice-dev-green --version-label <LKG>`
- Observacion con `aws-observability`; registrar `phase: result` y `transition.py rollback_finished`.

## 6. Evidencia obligatoria
`rollback-*.json` (precheck y result): from_version, to_version, update_accepted_prior,
failure_class, lkg_usable, lkg_images_present, option_settings_required, prior_rollback_attempts,
result y final_state.

## 7. STOP
- Cualquier condicion no demostrada: `escalate`.
- Rollback fallido o environment no sano tras rollback: `rollback_finished` -> BLOCKED_HUMAN.
- El resultado de un rollback exitoso tambien termina en BLOCKED_HUMAN (el release fallo).

## 8. Fuentes
- `docs/cicd/TPI_Contrato_CICD_AWS_v2.md` principio 9 y seccion 4 (rollback operativo).
- `docs/cicd/LECCIONES_DEPLOY_AWS_H3_2_H3_3.md` LL-06; extracto v1 punto 7.
- `harness/policies.yaml` `rollback_authorization`.
