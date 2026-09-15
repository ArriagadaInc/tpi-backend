---
name: tpi-release-readiness
role: reviewer
load_when: "CANDIDATE_REVIEW"
sources: [release_contract_v2, aws_lessons, aws_lessons_extracts, aws_policy, bundle_builder, domain_locked_template, candidate_verifier, publish_workflow, mcp_setup]
---

# tpi-release-readiness

## 1. Cuando se carga
CANDIDATE_REVIEW: revision automatica del release candidate real antes del Human Gate.

## 2. Puede
- Reconstruir el bundle domain-locked y comparar SHA256.
- Lecturas AWS via `aws_guard.py` (modo candidate_read). Solo desde Claude Code.
- Consultar `gh run view` del publish ECR.

## 3. No puede
- Construir o publicar imagenes, subir a S3, crear Application Versions, desplegar.

## 4. Precondiciones
- `candidate-*.json`, `merge-*.json` y `review-*.json` aprobada presentes; `git fetch origin main`.

## 5. Comandos y herramientas
- `git rev-parse <release_sha>^{tree}` == `reviewed_tree` de la revision.
- `gh run view <publish_run_id> --json conclusion,headSha`.
- Reconstruccion: `python -c` con `build_domain_locked_bundle(template=deployment/aws/docker-compose.domainlocked.yml, ...)`
  en un directorio temporal y `sha256sum`.
- `python scripts/harness/aws_guard.py ecr describe-images --repository-name tpi-dev-app --image-ids imageDigest=<digest>`
- `python scripts/harness/aws_guard.py ecr describe-image-scan-findings --repository-name <repo> --image-id imageDigest=<digest>`
- `python scripts/harness/aws_guard.py elasticbeanstalk describe-application-versions --application-name tpi-backoffice --version-labels <candidate> <lkg>`
- `python scripts/harness/aws_guard.py s3api head-object --bucket <bucket> --key <key> --checksum-mode ENABLED`
- `python scripts/harness/aws_guard.py elasticbeanstalk describe-environments --application-name tpi-backoffice --environment-names tpi-backoffice-dev-green --no-include-deleted`

## 6. Evidencia obligatoria
Checks (PASS/FAIL) en `candidate_review-*.json`:
- `release_tree_equals_reviewed_tree` y `release_sha_on_main`.
- `publish_run_success_for_release_sha`.
- `digests_exist_and_immutable`, `ecr_scan_high_critical_zero`.
- `bundle_reproducible_sha256_match`, `bundle_only_compose_no_build_no_legacy_domain`.
- `s3_object_checksum_matches_bundle`, `application_version_source_bundle_matches`.
- `identity_chain_complete` (commit -> digests -> bundle -> key -> AV).
- `lkg_is_observed_healthy_version`, `lkg_application_version_usable`, `lkg_all_digests_present_in_ecr`.
- `no_secrets_in_bundle_or_evidence`, `smoke_plan_present`.
Decision `APPROVED` con `cause: null`, o `REJECTED` con `cause` `code` / `artifact` / `infra`.

## 7. STOP
- Cualquier desajuste de hash, digest, arbol o label: REJECTED (no se solicita Human Gate).
- Digests del LKG ausentes (ECR lifecycle keep-20): REJECTED `infra`.
- AccessDenied o estado AWS ambiguo: REJECTED `infra` con evidencia.

## 8. Fuentes
- `docs/cicd/TPI_Contrato_CICD_AWS_v2.md` secciones 1, 3, 5, 12.
- `docs/AWS_DEPLOYMENT_BEST_PRACTICES.md` principios 1, 3, 9; `docs/cicd/LECCIONES_DEPLOY_AWS_H3_2_H3_3.md` LL-03, LL-13.
