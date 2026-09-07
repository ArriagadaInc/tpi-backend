#!/usr/bin/env bash
set -euo pipefail

readonly ACCOUNT_ID="821656895812"
readonly REGION="us-east-2"
readonly PIPELINE_NAME="tpi-backoffice-dev-promotion"
readonly PIPELINE_DEFINITION="deployment/aws/tpi-dev-eb-pipeline.json"
readonly RELEASE_BUCKET="tpi-dev-release-artifacts-821656895812-us-east-2"
readonly SOURCE_KEY="promotions/h3-3-crm-web-28cf009-r1/candidate-data.zip"
readonly PROMOTE_STAGE="Promote"
readonly DISABLE_REASON="Promotion not authorized - provisioning validation"
readonly APPLICATION="tpi-backoffice"
readonly ENVIRONMENT="tpi-backoffice-dev-green"
readonly CURRENT_VERSION="h2-5d-ecr-47fa0c9"
readonly CANDIDATE_VERSION="h3-3-crm-web-28cf009-r1"
readonly CANDIDATE_BUCKET="elasticbeanstalk-us-east-2-821656895812"
readonly CANDIDATE_KEY="tpi-backoffice/dev-releases/h3-3-crm-web-28cf009-r1/tpi-dev-ecr-28cf009.zip"
readonly PIPELINE_ROLE="arn:aws:iam::821656895812:role/tpi-codepipeline-dev-eb-role"

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

pipeline_json="$(aws codepipeline get-pipeline \
  --region "$REGION" \
  --name "$PIPELINE_NAME" \
  --output json)"

jq -e --arg role "$PIPELINE_ROLE" --arg bucket "$RELEASE_BUCKET" --arg key "$SOURCE_KEY" '
  .pipeline.pipelineType == "V2"
  and .pipeline.executionMode == "QUEUED"
  and .pipeline.roleArn == $role
  and .pipeline.stages[0].name == "Source"
  and .pipeline.stages[0].actions[0].configuration.S3Bucket == $bucket
  and .pipeline.stages[0].actions[0].configuration.S3ObjectKey == $key
  and .pipeline.stages[0].actions[0].configuration.AllowOverrideForS3ObjectKey == "false"
  and .pipeline.stages[0].actions[0].configuration.PollForSourceChanges == "false"
' <<<"$pipeline_json" >/dev/null || fail "physical pipeline does not match the approved contract"

pipeline_state="$(aws codepipeline get-pipeline-state \
  --region "$REGION" \
  --name "$PIPELINE_NAME" \
  --output json)"
jq -e --arg stage "$PROMOTE_STAGE" '
  [.stageStates[] | select(.stageName == $stage and .inboundTransitionState.enabled == false)]
  | length == 1
' <<<"$pipeline_state" >/dev/null || fail "Promote inbound transition is not disabled"

echo "Waiting for the automatic CreatePipeline execution to fail in Source."
execution_id=""
execution_status=""
execution_trigger=""
for _ in $(seq 1 60); do
  executions="$(aws codepipeline list-pipeline-executions \
    --region "$REGION" \
    --pipeline-name "$PIPELINE_NAME" \
    --max-results 10 \
    --output json)"
  execution_id="$(jq -r '.pipelineExecutionSummaries[0].pipelineExecutionId // empty' <<<"$executions")"
  execution_status="$(jq -r '.pipelineExecutionSummaries[0].status // empty' <<<"$executions")"
  execution_trigger="$(jq -r '.pipelineExecutionSummaries[0].trigger.triggerType // "unknown"' <<<"$executions")"

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
test "$execution_trigger" = "CreatePipeline" || fail "unexpected bootstrap trigger: $execution_trigger"

actions="$(aws codepipeline list-action-executions \
  --region "$REGION" \
  --pipeline-name "$PIPELINE_NAME" \
  --filter "pipelineExecutionId=$execution_id" \
  --output json)"

jq -e '
  [.actionExecutionDetails[] | select(.stageName == "Promote")] | length == 0
' <<<"$actions" >/dev/null || fail "unsafe bootstrap: execution reached Promote"
jq -e '
  [.actionExecutionDetails[]
    | select(.stageName == "Source" and .status == "Failed" and (.errorDetails.message | length > 0))]
  | length >= 1
' <<<"$actions" >/dev/null || fail "bootstrap did not fail with evidence in Source"

environment_json="$(aws elasticbeanstalk describe-environments \
  --region "$REGION" \
  --application-name "$APPLICATION" \
  --environment-names "$ENVIRONMENT" \
  --no-include-deleted \
  --output json)"
jq -e --arg application "$APPLICATION" --arg environment "$ENVIRONMENT" --arg version "$CURRENT_VERSION" '
  .Environments | length == 1
  and .[0].ApplicationName == $application
  and .[0].EnvironmentName == $environment
  and .[0].VersionLabel == $version
  and .[0].Status == "Ready"
  and .[0].Health == "Green"
  and .[0].HealthStatus == "Ok"
' <<<"$environment_json" >/dev/null || fail "Elastic Beanstalk baseline changed during bootstrap"

candidate_json="$(aws elasticbeanstalk describe-application-versions \
  --region "$REGION" \
  --application-name "$APPLICATION" \
  --version-labels "$CANDIDATE_VERSION" \
  --output json)"
jq -e \
  --arg candidate "$CANDIDATE_VERSION" \
  --arg bucket "$CANDIDATE_BUCKET" \
  --arg key "$CANDIDATE_KEY" '
  .ApplicationVersions | length == 1
  and .[0].VersionLabel == $candidate
  and .[0].Status != "FAILED"
  and .[0].SourceBundle.S3Bucket == $bucket
  and .[0].SourceBundle.S3Key == $key
' <<<"$candidate_json" >/dev/null || fail "candidate Application Version is not intact"

jq -n \
  --arg pipeline "$PIPELINE_NAME" \
  --arg execution_id "$execution_id" \
  --arg trigger "$execution_trigger" \
  --arg status "$execution_status" \
  --arg source_error "$(jq -r '[.actionExecutionDetails[] | select(.stageName == "Source")][0].errorDetails.message' <<<"$actions")" \
  '{pipeline: $pipeline, bootstrap_execution_id: $execution_id, trigger: $trigger, status: $status, source_error: $source_error, promote_executed: false, promote_inbound_enabled: false}'
