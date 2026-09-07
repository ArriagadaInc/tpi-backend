#!/usr/bin/env bash
set -euo pipefail

readonly ACCOUNT_ID="821656895812"
readonly REGION="us-east-2"
readonly PIPELINE_NAME="tpi-backoffice-dev-promotion"
readonly PIPELINE_DEFINITION="deployment/aws/tpi-dev-eb-pipeline.json"
readonly BOOTSTRAP_VALIDATOR="scripts/release/validate_dev_codepipeline_bootstrap.sh"
readonly RELEASE_BUCKET="tpi-dev-release-artifacts-821656895812-us-east-2"
readonly SOURCE_KEY="promotions/h3-3-crm-web-28cf009-r1/candidate-data.zip"
readonly PROMOTE_STAGE="Promote"
readonly DISABLE_REASON="Promotion not authorized - provisioning validation"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null || fail "required command is unavailable: $1"
}

for command_name in aws grep jq seq sleep; do
  require_command "$command_name"
done

test -f "$PIPELINE_DEFINITION" || fail "pipeline definition not found: $PIPELINE_DEFINITION"
test -f "$BOOTSTRAP_VALIDATOR" || fail "bootstrap validator not found: $BOOTSTRAP_VALIDATOR"

actual_account="$(aws sts get-caller-identity --query Account --output text)"
test "$actual_account" = "$ACCOUNT_ID" || fail "wrong AWS account: $actual_account"

echo "Checking that the bootstrap source object is absent."
set +e
source_error="$(aws s3api head-object \
  --region "$REGION" \
  --bucket "$RELEASE_BUCKET" \
  --key "$SOURCE_KEY" 2>&1)"
source_status=$?
set -e

if [ "$source_status" -eq 0 ]; then
  fail "bootstrap source already exists; refusing to create pipeline: s3://$RELEASE_BUCKET/$SOURCE_KEY"
fi
if ! grep -Eq '(^|[^0-9])404([^0-9]|$)|Not Found|NoSuchKey' <<<"$source_error"; then
  fail "unable to prove bootstrap source absence: $source_error"
fi

echo "Checking that the pipeline does not already exist."
set +e
pipeline_error="$(aws codepipeline get-pipeline \
  --region "$REGION" \
  --name "$PIPELINE_NAME" 2>&1)"
pipeline_status=$?
set -e

if [ "$pipeline_status" -eq 0 ]; then
  fail "pipeline already exists; bootstrap is create-only: $PIPELINE_NAME"
fi
if ! grep -q 'PipelineNotFoundException' <<<"$pipeline_error"; then
  fail "unable to prove pipeline absence: $pipeline_error"
fi

echo "Creating pipeline; AWS will start one automatic bootstrap execution."
aws codepipeline create-pipeline \
  --region "$REGION" \
  --cli-input-json "file://$PIPELINE_DEFINITION" \
  >/dev/null

echo "Disabling the Promote inbound transition before inspecting the bootstrap execution."
aws codepipeline disable-stage-transition \
  --region "$REGION" \
  --pipeline-name "$PIPELINE_NAME" \
  --stage-name "$PROMOTE_STAGE" \
  --transition-type Inbound \
  --reason "$DISABLE_REASON"

echo "Waiting for the automatic CreatePipeline execution to fail in Source."
execution_id=""
execution_status=""
for _ in $(seq 1 60); do
  executions="$(aws codepipeline list-pipeline-executions \
    --region "$REGION" \
    --pipeline-name "$PIPELINE_NAME" \
    --max-results 10 \
    --output json)"
  execution_id="$(jq -r '.pipelineExecutionSummaries[0].pipelineExecutionId // empty' <<<"$executions")"
  execution_status="$(jq -r '.pipelineExecutionSummaries[0].status // empty' <<<"$executions")"
  case "$execution_status" in
    Failed) break ;;
    Succeeded|Superseded|Stopped|Cancelled)
      fail "bootstrap execution reached unexpected terminal status: $execution_status"
      ;;
  esac
  sleep 2
done

test -n "$execution_id" || fail "automatic CreatePipeline execution was not observed"
test "$execution_status" = "Failed" || fail "bootstrap execution did not fail within timeout"

bash "$BOOTSTRAP_VALIDATOR" "$execution_id"
