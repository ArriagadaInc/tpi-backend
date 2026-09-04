#!/usr/bin/env bash
set -euo pipefail

: "${ARTIFACT_DIR:=artifact}"
: "${BUNDLE_NAME:?BUNDLE_NAME is required}"
: "${MANIFEST_NAME:?MANIFEST_NAME is required}"
: "${BUNDLE_SHA256:?BUNDLE_SHA256 is required}"
: "${SOURCE_SHA:?SOURCE_SHA is required}"
: "${APP_IMAGE:?APP_IMAGE is required}"
: "${CADDY_IMAGE:?CADDY_IMAGE is required}"

bundle="$ARTIFACT_DIR/$BUNDLE_NAME"
manifest="$ARTIFACT_DIR/$MANIFEST_NAME"

echo "Downloaded artifact layout:"
find "$ARTIFACT_DIR" -maxdepth 2 -type f -printf '%P\n' | sort

if [[ ! -f "$bundle" ]]; then
  echo "ERROR: expected bundle not found: $bundle"
  exit 1
fi
if [[ ! -f "$manifest" ]]; then
  echo "ERROR: expected manifest not found: $manifest"
  exit 1
fi

file_count="$(find "$ARTIFACT_DIR" -type f | wc -l)"
if [[ "$file_count" -ne 2 ]]; then
  echo "ERROR: expected exactly 2 artifact files, found $file_count"
  exit 1
fi

actual_bundle_sha="$(sha256sum "$bundle" | awk '{print $1}')"
if [[ "$actual_bundle_sha" != "$BUNDLE_SHA256" ]]; then
  echo "ERROR: bundle SHA256 mismatch"
  echo "Expected: $BUNDLE_SHA256"
  echo "Actual:   $actual_bundle_sha"
  exit 1
fi

if ! jq -e \
  --arg runtime "$SOURCE_SHA" \
  --arg app "$APP_IMAGE" \
  --arg caddy "$CADDY_IMAGE" \
  --arg bundle_sha "$BUNDLE_SHA256" \
  '.runtime_git_sha == $runtime
   and .app_image == $app
   and .caddy_image == $caddy
   and .bundle_sha256 == $bundle_sha' \
  "$manifest" >/dev/null; then
  echo "ERROR: manifest does not match the frozen candidate"
  exit 1
fi

zip_entries="$(zipinfo -1 "$bundle" 2>&1)" || {
  echo "ERROR: ZIP listing failed"
  echo "$zip_entries"
  exit 1
}
if [[ "$zip_entries" != "docker-compose.yml" ]]; then
  echo "ERROR: bundle must contain only docker-compose.yml"
  printf '%s\n' "$zip_entries"
  exit 1
fi

if ! unzip -t "$bundle" >/dev/null; then
  echo "ERROR: ZIP integrity validation failed"
  exit 1
fi

bundle_dir="$(mktemp -d)"
trap 'rm -rf "$bundle_dir"' EXIT
unzip -q "$bundle" -d "$bundle_dir"
compose="$bundle_dir/docker-compose.yml"

app_occurrences="$(grep -F -c -- "$APP_IMAGE" "$compose" || true)"
if [[ "$app_occurrences" -ne 2 ]]; then
  echo "ERROR: expected app digest twice in docker-compose.yml, found $app_occurrences"
  exit 1
fi

caddy_occurrences="$(grep -F -c -- "$CADDY_IMAGE" "$compose" || true)"
if [[ "$caddy_occurrences" -ne 1 ]]; then
  echo "ERROR: expected Caddy digest once in docker-compose.yml, found $caddy_occurrences"
  exit 1
fi

if ! (
  export TPI_APP_IMAGE="$APP_IMAGE"
  export TPI_CADDY_IMAGE="$CADDY_IMAGE"
  export DATABASE_HOST=ci-placeholder.invalid
  export DATABASE_NAME=tpi
  export DATABASE_USER=tpi_app
  export DATABASE_PASSWORD=ci-not-a-secret
  export API_IDEMPOTENCY_HMAC_SECRET=ci-not-a-secret
  export AUTH_USERS_JSON='{"users":[]}'
  export WEB_SESSION_SECRET=ci-web-session-secret-not-for-runtime
  export TPI_PUBLIC_SITE_URL=https://dev.example.test
  export TPI_PUBLIC_SITE_ADDRESS=https://dev.example.test
  export TPI_BACKOFFICE_SITE_ADDRESS=https://backoffice.dev.example.test
  docker compose -f "$compose" config --quiet
); then
  echo "ERROR: docker compose config validation failed"
  exit 1
fi

echo "Artifact verification passed."
