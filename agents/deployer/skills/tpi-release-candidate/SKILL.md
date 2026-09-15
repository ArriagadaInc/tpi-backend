---
name: tpi-release-candidate
role: deployer
load_when: "MERGING y PREPARING_DEPLOYMENT"
sources: [release_contract_v2, publish_workflow, bundle_builder, domain_locked_template, candidate_verifier, aws_lessons]
---

# tpi-release-candidate

## 1. Cuando se carga
Merge del arbol revisado y fabricacion unica del candidate (imagenes + bundle).

## 2. Puede
- MERGING: `gh pr merge <pr> --squash --match-head-commit <reviewed_sha>`; `git fetch origin main`.
- PREPARING: `gh workflow run publish-dev-ecr-images.yml -f source_sha=<release_sha>`; observar y
  descargar el artifact; construir el bundle domain-locked en `.harness-release/`.

## 3. No puede
- Mergear con auto-merge o sin `--match-head-commit`; mergear si el PR no esta al dia con main.
- Reconstruir imagenes localmente, usar tags mutables o digests historicos.
- Modificar codigo, workflows o el template de compose.

## 4. Precondiciones
- MERGING: revision APPROVED sobre el `head_sha` actual del PR y CI verde.
- PREPARING: `merge-*.json` valido; `release_sha` en `origin/main`.

## 5. Comandos y herramientas
- `git rev-parse <release_sha>^{tree}` debe ser igual a `reviewed_tree`; si no: `merge_failed`.
- `gh run list --workflow publish-dev-ecr-images.yml --limit 5 --json databaseId,headSha,conclusion`
- `gh run watch <run_id>`; `gh run download <run_id> --dir .harness-release/<release_sha7>/artifact`
- Digests desde el manifest descargado (nunca escritos a mano).
- Bundle: `python -c "from pathlib import Path; from deployment.build_eb_ecr_bundle import build_domain_locked_bundle as b; print(b(template=Path('deployment/aws/docker-compose.domainlocked.yml'), output=Path('.harness-release/<label>.zip'), app_image='<repo>@<digest>', caddy_image='<repo>@<digest>', runtime_git_sha='<release_sha>'))"`
- Version label: `h3-<slug>-<release_sha7>-domainlocked-r1` (patron de `environments/dev.yaml`; nunca reutilizar).

## 6. Evidencia obligatoria
- `merge-*.json`: pr_number, reviewed_sha, reviewed_tree, release_sha, release_tree, main_parent_sha,
  method `squash`, match_head_commit_used `true`.
- En `candidate-*.json`: publish_run, images (repository, digest, scan), bundle (sha256,
  artifact_type `domain-locked`, reproducible).

## 7. STOP
- Merge rechazado o arbol distinto: `merge_failed` (no forzar ni rebasear por cuenta propia).
- Workflow publish fallido o scan HIGH/CRITICAL: `preparation_failed`.
- Manifest inconsistente con el release SHA.

## 8. Fuentes
- `docs/cicd/TPI_Contrato_CICD_AWS_v2.md` secciones 1 (principios 1, 10), 3 (pasos 1-3, 11).
- `.github/workflows/publish-dev-ecr-images.yml`; `deployment/build_eb_ecr_bundle.py`.
- `docs/AWS_DEPLOYMENT_BEST_PRACTICES.md` antipatrones (tags mutables, regenerar candidate).
