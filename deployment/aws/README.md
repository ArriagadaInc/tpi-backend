# AWS immutable image deployment

`docker-compose.ecr.yml` is only for Elastic Beanstalk DEV. It references
immutable ECR images and intentionally contains no `build:` section. Local
development continues to use the root `docker-compose.yml` and
`docker-compose.local.yml`.

Before a deployment, GitHub Actions runs the `Publish immutable DEV images to
ECR` workflow with a full Git SHA from `feat/h2-5-simple-dev-auth`. The workflow
runs all quality gates before it builds and pushes both images:

- `tpi-dev-app:<full-git-sha>` for FastAPI and Streamlit.
- `tpi-dev-caddy:<full-git-sha>` for Caddy and the static frontend.

Elastic Beanstalk receives `TPI_ECR_REGISTRY` and `TPI_IMAGE_TAG` as deployment
configuration, then only pulls and starts the approved images. Runtime secrets
remain external environment secrets; they are never stored in this Compose file.
