---
name: tpi-cicd-review
role: reviewer
load_when: "REVIEWING si el diff toca .github/, deployment/, scripts/release/, Dockerfile*, compose o lockfiles"
sources: [release_contract_v2, aws_lessons, aws_lessons_extracts, release_contract_v1_extract, codepipeline_architecture, ci_workflow, publish_workflow]
---

# tpi-cicd-review

## 1. Cuando se carga
PRs de tooling de CI/CD, empaquetado o infraestructura versionada (clase C) y cambios de lockfiles.

## 2. Puede
- Leer workflows, scripts y policies IAM versionadas; correr `actionlint` y tests de contrato.
- Consultar AWS MCP (solo conocimiento) para validar parametros y cuotas documentadas.

## 3. No puede
- Disparar workflows, aplicar IAM, leer recursos AWS en REVIEWING.

## 4. Precondiciones
- Clase de cambio declarada; en clase C, plan y rollback descritos en el PR.

## 5. Comandos y herramientas
- `docker run --rm -v "$PWD:/repo:ro" rhysd/actionlint:1.7.7 /repo/.github/workflows/<wf>.yml`
- `pytest tests/security tests/unit -q -k "codepipeline or eb_ or ecr or bundle or oidc"`

## 6. Evidencia obligatoria
Checks (PASS/FAIL):
- `change_class_not_mixed` (A-E, contrato seccion 2).
- `no_hardcoded_historical_sha_digest_label` en workflows/scripts.
- `images_by_digest_no_mutable_tags`.
- `no_option_settings_in_release_path`, `no_describe_configuration_settings`.
- `iam_complete_contract_not_access_denied_driven` (contrato seccion 7; LL-09).
- `aws_quotas_and_optional_fields_tested` (BEST_PRACTICES principios 5-7).
- `no_or_true_on_critical_evidence` (extracto v1).
- `github_no_direct_eb_write` (separacion de poderes).

## 7. STOP
- Un cambio de infraestructura viaja con un cambio funcional: REJECTED.
- Se agrega un permiso IAM puntual tras un AccessDenied sin contrato completo: REJECTED blocker.

## 8. Fuentes
- `docs/cicd/TPI_Contrato_CICD_AWS_v2.md` secciones 2, 4, 6, 7, 13.
- `docs/AWS_DEPLOYMENT_BEST_PRACTICES.md` principios y antipatrones (lecciones).
- `docs/cicd/LECCIONES_DEPLOY_AWS_H3_2_H3_3.md`; `docs/cicd/CONTRATO_CICD_AWS_V1_EXTRACTO.md`.
- `docs/DEV_EB_CODEPIPELINE_ARCHITECTURE.md` solo para tareas H3.2/infra path.
