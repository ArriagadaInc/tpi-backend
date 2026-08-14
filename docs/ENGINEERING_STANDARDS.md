# Engineering Standards

## Definition of Done

A feature is not complete merely because it works locally. Before a pull request is approved, apply the controls that match its risk and scope:

- Unit tests for changed behavior and error handling.
- Integration tests for database, service, or external-boundary behavior.
- E2E tests for critical user flows.
- Full regression suite with global coverage at or above 80 percent.
- Ruff, Black, and MyPy.
- Bandit at medium severity and confidence or higher.
- `pip-audit` against the versioned runtime dependency lock.
- Docker image build when the change affects the deployable application.
- No secrets in code, logs, test data, or documentation.
- Externalized environment configuration and safe stdout/stderr logging.
- Updated operational documentation and `docs/BITACORA.md`.
- Pull request opened against the target branch with all CI jobs green.

Tests must validate behavior and risk. Do not add tests solely to raise coverage.

## Dependency Reproducibility

- `requirements/runtime.lock` is the exact runtime dependency set used by Docker and audited by CI.
- `requirements/dev.lock` extends the runtime lock with exact test and quality-tool versions used by CI.
- `pyproject.toml` expresses the supported dependency contract; the lock files choose the approved concrete versions.
- Update lock files only in a dedicated or clearly described pull request and run the full quality suite before merge.
- Docker installs the runtime lock first and installs the application with `--no-deps`, preventing accidental dependency upgrades during image builds.
