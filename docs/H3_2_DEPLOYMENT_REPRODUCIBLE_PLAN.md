# H3.2 Deployment Reproducible & Runbook

## Status

Phase 0: inventory and design.

## Goal

Define and later enforce a reproducible release chain:

```text
Git SHA
  ↓
CI approved
  ↓
Docker app built from that SHA
  ↓
immutable ECR digest
  ↓
release manifest
  ↓
EB bundle with that digest
  ↓
Application Version
  ↓
Green Environment
  ↓
runtime verification
  ↓
smoke
  ↓
cutover
  ↓
rollback available
```

## AS-IS Inventory

| Component | Current state | Gap / risk | H3.2 target state |
| --- | --- | --- | --- |
| `.github/workflows/ci.yml` | Validates code, tests, security, docker, and a canonical EB bundle | CI can still validate or publish against a historical bundle definition if the bundle inputs remain hardcoded | CI produces a release manifest and bundle inputs derived from the validated commit |
| `deployment/build_eb_ecr_bundle.py` | Builds a minimal ZIP from fixed CLI inputs | Runtime SHA and image digests are manually passed and can drift from the approved commit | Bundle consumes a manifest or verified metadata derived from the commit |
| `deployment/aws/` | Contains environment-specific deployment helpers and notes | Runtime verification, cutover, and rollback are still mostly manual | Preflight and runtime verification become scripted and repeatable |
| `deployment/ecr/` | Lifecycle policy only | No direct release linkage to the bundle or manifest | ECR digests are tied to a release manifest |
| `deployment/caddy/` | Custom Caddy build and ACME Route53 setup | Image digest correctness is validated indirectly and manually at runtime | Caddy digest is recorded in the release manifest and verified before deployment |
| `deployment/iam/` | Least-privilege policies for the environments | No release artifact links IAM state to the bundle/runtime chain | IAM remains separate but is checked by preflight gates |
| `docs/DEPLOYMENT.md` | Legacy, non-TPI, non-EB oriented deployment guide | Not a current runbook for H2.5/H3.1 blue/green release | Replaced by a TPI-specific deployment runbook |
| `docs/H2_2_AWS_DEV_DEPLOYMENT.md` and related H2/H3 docs | Capture prior milestones and operational context | Fragmented deployment knowledge across milestones | Consolidated deployment playbook and checklist |

## Gaps Identified

- SHA and digest values are still hardcoded in the EB bundle generation path.
- CI can pass even when the bundle parameters do not match the runtime that was actually validated.
- There is no single artifact proving the chain SHA → image → digest → bundle → EB version → runtime.
- The post-merge `push/main` run for the final merge commit was not observable in the available workflow backend snapshot.
- Runtime verification still requires manual inspection of the environment and container digests.
- Smoke, cutover, and rollback are described operationally but remain too manual.
- `test_lead_deleted` observability is not yet durable enough for a low-friction automated rollback/smoke decision.

## Release Contract

The release contract is split into two immutable artifacts:

- `release-manifest.json` = expected declaration.
- `release-verification.json` = observed AWS/runtime evidence.

The manifest stays external to the ZIP. This avoids circularity with
`bundle_sha256`, which can only be known after the bundle exists.

Proposed manifest schema:

```json
{
  "schema_version": "1.0",
  "release_id": "tpi-ad22d37",
  "git_sha": "ad22d37048176aa80ab139f56c3ef6903f6e430e",
  "git_tree_sha": "...",
  "app_image": {
    "reference": "821656895812.dkr.ecr.us-east-2.amazonaws.com/tpi-dev-app@sha256:...",
    "source_git_sha": "ad22d37048176aa80ab139f56c3ef6903f6e430e"
  },
  "caddy_image": {
    "reference": "821656895812.dkr.ecr.us-east-2.amazonaws.com/tpi-dev-caddy@sha256:...",
    "source_git_sha": "..."
  },
  "bundle": {
    "filename": "tpi-release-ad22d37.zip",
    "sha256": "..."
  },
  "target": {
    "environment": "aws-dev",
    "eb_version": "tpi-ad22d37"
  },
  "ci": {
    "repository": "ArriagadaInc/tpi-backend",
    "run_id": "...",
    "run_attempt": 1
  },
  "generated_at": "..."
}
```

### Mandatory fields

- `schema_version`
- `release_id`
- `git_sha`
- `git_tree_sha`
- `app_image`
- `caddy_image`
- `bundle`
- `target`
- `ci`
- `generated_at`

### Generation responsibility

- CI generates the manifest after verifying the commit, building immutable images, and producing the EB bundle.
- The bundle builder computes `bundle.sha256` after writing the ZIP.
- The publish/deploy workflow attaches the manifest to the release artifact and records the run metadata.

### Auto-computable fields

- `schema_version`
- `release_id`
- `git_sha` when sourced from the validated commit context
- `git_tree_sha` when derived from the checked-out tree
- `bundle.sha256`
- `generated_at`

### Must be verified against AWS

- `app_image.reference`
- `caddy_image.reference`
- `target.eb_version`
- `target.environment`

### Stop rules for the manifest

- If `git_sha` does not match the validated commit, stop.
- If `git_tree_sha` does not match the checked-out content hash strategy, stop.
- If image digests are missing or not immutable, stop.
- If `bundle.sha256` does not match the produced ZIP, stop.
- If runtime images do not match the manifest, stop before smoke/cutover.
- If the EB version or environment differs from the intended release target, stop.
- If `ci.repository` or `ci.run_id` cannot be traced back to the approved run, stop.

### Source of truth

The release SHA must come from the actual checkout:

```text
git rev-parse HEAD
```

and the working tree must be clean. If either condition fails, stop.

The workflow input SHA must never be a hardcoded constant.

### Provenance

- App image provenance must be recorded with OCI metadata:
  - `org.opencontainers.image.revision=<git_sha>`
- Caddy may reuse a previously approved digest, but its `source_git_sha` must still be explicit in the manifest.

## Proposed Components

```text
deployment/
├── preflight.py
├── build_eb_ecr_bundle.py
├── verify_release.py
├── smoke/
│   ├── api.py
│   └── backoffice.py
└── README.md
```

### `deployment/preflight.py`

- Inputs: environment names, baseline SHA, expected runtime metadata.
- Outputs: pass/fail with explicit reasons.
- Exit codes: non-zero on any mismatch.
- Responsibility: verify release prerequisites before build, deploy, or cutover.

### `deployment/build_eb_ecr_bundle.py`

- Inputs: template, app image digest, caddy image digest, runtime Git SHA.
- Outputs: minimal ZIP bundle and manifest.
- Exit codes: non-zero if the compose references drift from the approved digests.
- Responsibility: create the immutable EB source bundle.

### `deployment/verify_release.py`

- Inputs: `release-manifest.json`, AWS environment name, expected runtime digests.
- Outputs: `release-verification.json` or stop reasons.
- Exit codes: non-zero if runtime or bundle state diverges.
- Responsibility: compare expected release state against observed AWS/runtime state.

### `release-verification.json`

Example shape:

```json
{
  "manifest_sha256": "...",
  "environment": "tpi-backoffice-dev-green",
  "observed_eb_version": "...",
  "observed_app_image": "registry/repo@sha256:...",
  "observed_caddy_image": "registry/repo@sha256:...",
  "health": "Green",
  "status": "PASS",
  "verified_at": "..."
}
```

### `deployment/smoke/api.py`

- Inputs: public API URL or controlled host resolution.
- Outputs: API smoke results.
- Exit codes: non-zero on functional failure.

### `deployment/smoke/backoffice.py`

- Inputs: backoffice URL, credentials, test-lead scenario.
- Outputs: backoffice smoke and cleanup results.
- Exit codes: non-zero on functional failure.

## Stop Rules

- CI FAIL → NO DEPLOY
- SHA != image source → NO DEPLOY
- image without digest → NO DEPLOY
- bundle != manifest → NO DEPLOY
- runtime != release manifest → NO SMOKE / NO CUTOVER
- Green != Ready/Green/Ok → NO CUTOVER
- smoke FAIL → NO CUTOVER
- cutover FAIL → ROLLBACK
- same infrastructure error twice → STOP and diagnose

## Blue/Green Strategy

```text
BLUE   = current public environment
GREEN  = candidate environment

Deploy  → GREEN
Verify  → GREEN
Smoke   → GREEN
Swap CNAME
Verify public

Rollback = reverse swap
```

The previous environment must remain available until public validation and smoke are complete.

## Roadmap

- Phase 0 — Inventory and design
- Phase 1 — Release manifest + SHA/digest reproducibility
- Phase 2 — Automated preflight
- Phase 3 — Reproducible CI/CD
- Phase 4 — Runtime verification
- Phase 5 — Automated smoke
- Phase 6 — Blue/Green + rollback
- Phase 7 — Observability and runbook
- Phase 8 — End-to-end H3.2 rehearsal

## Out of Scope

- CRM functionality changes
- PostgreSQL schema changes
- migrations
- new business rules
- H3.3
- visual redesign
- unnecessary AWS changes

## Phase 1 Recommendation

Do not implement yet.
First confirm the design, then add the release manifest and reproducibility checks in a small, isolated commit series.
