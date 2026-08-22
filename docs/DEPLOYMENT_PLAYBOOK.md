# Deployment Playbook

## Purpose

Short operational playbook for the TPI DEV release lifecycle.

## Sections

- Baseline confirmation
- SHA and tree provenance
- Release manifest
- Bundle validation
- Green deployment
- Runtime verification
- Smoke validation
- Cutover
- Rollback
- Observability

## Status

Skeleton created during H3.2 Phase 0.

## Deterministic Naming

- Release naming must remain strict and deterministic.
- The current canonical bundle naming rule is SHA-derived.
- If the historical `h2-5d-ecr-<sha>.zip` naming is replaced with a neutral
  name such as `tpi-release-<sha>.zip`, the new rule must be equally strict and
  covered by tests.
