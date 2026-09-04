# AWS immutable image deployment

`docker-compose.ecr.yml` is only for Elastic Beanstalk DEV. It references
immutable ECR images and intentionally contains no `build:` section. Local
development continues to use the root `docker-compose.yml` and
`docker-compose.local.yml`.

Before a deployment, GitHub Actions runs the `Publish immutable DEV images to
ECR` workflow manually with a required full Git SHA. The authorization step
accepts only a commit contained in `main` or the exact HEAD of an open
same-repository pull request targeting `main`, before any AWS credentials are
assumed. The workflow runs all quality gates before it builds and pushes both
images:

- `tpi-dev-app:<full-git-sha>` for FastAPI and Streamlit.
- `tpi-dev-caddy:<full-git-sha>` for Caddy and the static frontend.

Elastic Beanstalk receives `TPI_ECR_REGISTRY` and `TPI_IMAGE_TAG` as deployment
configuration, then only pulls and starts the approved images. Runtime secrets
remain external environment secrets; they are never stored in this Compose file.

After the ECR scan reports zero HIGH and CRITICAL findings, the workflow
creates `tpi-dev-ecr-<sha7>.zip` and its manifest with the resolved immutable
digests. The bundle is uploaded as a release artifact and is not deployed
automatically.

Promotion to Elastic Beanstalk is orchestrated through the dedicated V2
CodePipeline declared in `tpi-dev-eb-pipeline.json`. GitHub publishes a
data-only candidate to a fixed S3 key and starts that single pipeline with an
immutable `VersionId`; it does not call Elastic Beanstalk write APIs. The
pipeline downloads hash-pinned promotion tooling from a protected S3 prefix
that the GitHub role cannot modify, then uses its AWS service role and the
version-aware implementation in `promote_eb_candidate.py`.
