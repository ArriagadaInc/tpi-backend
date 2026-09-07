#!/usr/bin/env bash
set -euo pipefail

readonly ACCOUNT_ID="821656895812"
readonly REGION="us-east-2"
readonly PIPELINE_NAME="tpi-backoffice-dev-promotion"
readonly RELEASE_BUCKET="tpi-dev-release-artifacts-821656895812-us-east-2"
readonly SOURCE_KEY="promotions/h3-3-crm-web-28cf009-r1/candidate-data.zip"
readonly PROMOTE_STAGE="Promote"
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

for command_name in aws grep jq; do
  require_command "$command_name"
done

test "$#" -eq 1 || fail "usage: $0 <bootstrap-execution-id>"
readonly EXECUTION_ID="$1"
test -n "$EXECUTION_ID" || fail "bootstrap execution ID must not be empty"

actual_account="$(aws sts get-caller-identity --query Account --output text)"
test "$actual_account" = "$ACCOUNT_ID" || fail "wrong AWS account: $actual_account"

pipeline_json="$(aws codepipeline get-pipeline \
  --region "$REGION" \
  --name "$PIPELINE_NAME" \
  --output json)"

jq -e --arg role "$PIPELINE_ROLE" --arg bucket "$RELEASE_BUCKET" --arg key "$SOURCE_KEY" '
  .pipeline.pipelineType == "V2"
  and .pipeline.executionMode == "QUEUED"
  and .pipeline.roleArn == $role
  and .pipeline.stages[0].name == "Source"
  and .pipeline.stages[0].actions[0].name == "ApprovedReleaseSource"
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

execution="$(aws codepipeline get-pipeline-execution \
  --region "$REGION" \
  --pipeline-name "$PIPELINE_NAME" \
  --pipeline-execution-id "$EXECUTION_ID" \
  --output json)"
jq -e --arg execution_id "$EXECUTION_ID" '
  .pipelineExecution.pipelineExecutionId == $execution_id
  and .pipelineExecution.status == "Failed"
  and .pipelineExecution.trigger.triggerType == "CreatePipeline"
' <<<"$execution" >/dev/null || fail "execution is not the expected failed CreatePipeline bootstrap"

actions="$(aws codepipeline list-action-executions \
  --region "$REGION" \
  --pipeline-name "$PIPELINE_NAME" \
  --filter "pipelineExecutionId=$EXECUTION_ID" \
  --output json)"

jq -e '
  .actionExecutionDetails | length == 1
  and .[0].stageName == "Source"
  and .[0].actionName == "ApprovedReleaseSource"
  and .[0].status == "Failed"
' <<<"$actions" >/dev/null || fail "bootstrap must contain exactly one failed ApprovedReleaseSource action"
jq -e '
  [.actionExecutionDetails[] | select(.stageName == "Promote")] | length == 0
' <<<"$actions" >/dev/null || fail "unsafe bootstrap: execution reached Promote"

echo "Rechecking that the exact bootstrap source remains absent after Source failed."
set +e
source_error="$(aws s3api head-object \
  --region "$REGION" \
  --bucket "$RELEASE_BUCKET" \
  --key "$SOURCE_KEY" 2>&1)"
source_status=$?
set -e

if [ "$source_status" -eq 0 ]; then
  fail "bootstrap source exists after failed Source action: s3://$RELEASE_BUCKET/$SOURCE_KEY"
fi
if ! grep -Eq '(^|[^0-9])404([^0-9]|$)|NotFound|NoSuchKey' <<<"$source_error"; then
  fail "unable to prove post-bootstrap source absence: $source_error"
fi

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

source_error_details="$(jq -r '
  .actionExecutionDetails[0].output.executionResult.errorDetails.message
  // .actionExecutionDetails[0].errorDetails.message
  // empty
' <<<"$actions")"
source_summary="$(jq -r '
  .actionExecutionDetails[0].output.executionResult.externalExecutionSummary
  // .actionExecutionDetails[0].externalExecutionSummary
  // empty
' <<<"$actions")"

jq -n \
  --arg pipeline "$PIPELINE_NAME" \
  --arg execution_id "$EXECUTION_ID" \
  --arg trigger "CreatePipeline" \
  --arg status "Failed" \
  --arg source_error "$source_error_details" \
  --arg source_summary "$source_summary" \
  '{pipeline: $pipeline, bootstrap_execution_id: $execution_id, trigger: $trigger, status: $status, source_error: $source_error, source_summary: $source_summary, source_absent: true, promote_executed: false, promote_inbound_enabled: false}'
