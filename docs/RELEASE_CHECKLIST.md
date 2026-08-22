# Release Checklist

## Preflight

- [ ] Baseline SHA confirmed
- [ ] Working tree clean
- [ ] CI result available
- [ ] Release manifest generated
- [ ] App image digest recorded
- [ ] Caddy image digest recorded
- [ ] Bundle SHA recorded
- [ ] `git_tree_sha` recorded
- [ ] CI run id recorded

## Build

- [ ] EB bundle contains only `docker-compose.yml`
- [ ] No `build:` directives in bundle
- [ ] Bundle matches manifest
- [ ] App image OCI revision matches commit
- [ ] Caddy image source provenance recorded

## Deploy

- [ ] GREEN updated
- [ ] Green is `Ready / Green / Ok`
- [ ] Runtime digests match the manifest
- [ ] `release-verification.json` produced

## Smoke

- [ ] Public HTTPS valid
- [ ] API responds
- [ ] Backoffice responds
- [ ] Functional smoke passes

## Cutover

- [ ] CNAME swap completed
- [ ] Public DNS resolves to GREEN
- [ ] Rollback environment preserved

## Post-release

- [ ] Logs reviewed
- [ ] Observability gaps logged
- [ ] Runbook updated
