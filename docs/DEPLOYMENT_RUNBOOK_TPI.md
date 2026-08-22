# TPI Deployment Runbook

## Purpose

Operational runbook for reproducible DEV releases, blue/green validation, and rollback.

## Current Status

Draft for H3.2 design. Not yet the authoritative execution guide.

## Required Inputs

- validated Git SHA
- clean working tree
- release manifest
- immutable app image digest
- immutable Caddy image digest
- EB version label
- target environment

## Source of Truth

- `git rev-parse HEAD` must equal the validated SHA.
- The working tree must be clean.
- The workflow must derive the release SHA from the checkout, not from a hardcoded constant.

## High-Level Flow

1. Confirm baseline and CI status.
2. Generate the expected `release-manifest.json`.
3. Build or select the EB bundle from immutable digests.
4. Verify `release-manifest.json` against the checked-out commit and bundle.
5. Deploy to GREEN.
6. Verify runtime digests and produce `release-verification.json`.
7. Run smoke tests.
8. Cut over.
9. Keep rollback available until stable.

## Stop Points

- CI failure
- manifest mismatch
- SHA mismatch
- runtime mismatch
- smoke failure
- public HTTPS failure
- unexpected AWS state

## Artifact Contract

- `release-manifest.json` is the expected declaration.
- `release-verification.json` is the observed evidence.
- The verification artifact must never mutate the manifest.

## Rollback Rule

Use the reverse blue/green swap. Do not destroy the previous environment during the release window.
