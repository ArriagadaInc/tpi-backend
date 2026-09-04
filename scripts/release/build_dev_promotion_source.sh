#!/usr/bin/env bash
set -euo pipefail

: "${ARTIFACT_DIR:=artifact}"
: "${PROMOTION_OUTPUT:?PROMOTION_OUTPUT is required}"

bash scripts/release/verify_frozen_candidate.sh

stage_dir="$(mktemp -d)"
trap 'rm -rf "$stage_dir"' EXIT
mkdir -p "$stage_dir/artifact" "$stage_dir/scripts/release" "$stage_dir/deployment/aws"
cp "$ARTIFACT_DIR/$BUNDLE_NAME" "$stage_dir/artifact/$BUNDLE_NAME"
cp "$ARTIFACT_DIR/$MANIFEST_NAME" "$stage_dir/artifact/$MANIFEST_NAME"
cp scripts/release/verify_frozen_candidate.sh "$stage_dir/scripts/release/"
cp deployment/aws/promote_eb_candidate.py "$stage_dir/deployment/aws/"

mkdir -p "$(dirname "$PROMOTION_OUTPUT")"
(
  cd "$stage_dir"
  zip -q -r "$OLDPWD/$PROMOTION_OUTPUT" artifact scripts deployment
)

echo "Promotion source SHA256: $(sha256sum "$PROMOTION_OUTPUT" | awk '{print $1}')"
