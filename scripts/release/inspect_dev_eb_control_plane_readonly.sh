#!/usr/bin/env bash
set -euo pipefail

readonly ACCOUNT_ID="821656895812"
readonly REGION="us-east-2"
readonly APPLICATION="tpi-backoffice"
readonly ENVIRONMENT="tpi-backoffice-dev-green"
readonly STACK_NAME="awseb-e-sd5gmkxr5r-stack"
readonly STACK_ARN="arn:aws:cloudformation:us-east-2:821656895812:stack/awseb-e-sd5gmkxr5r-stack/"

actual_account="$(aws sts get-caller-identity --query Account --output text)"
test "$actual_account" = "$ACCOUNT_ID" || {
  echo "ERROR: wrong AWS account: $actual_account" >&2
  exit 1
}

environment="$(aws elasticbeanstalk describe-environments \
  --region "$REGION" \
  --application-name "$APPLICATION" \
  --environment-names "$ENVIRONMENT" \
  --no-include-deleted \
  --query 'Environments[0].{ApplicationName:ApplicationName,EnvironmentName:EnvironmentName,EnvironmentId:EnvironmentId,VersionLabel:VersionLabel,Status:Status,Health:Health,HealthStatus:HealthStatus}' \
  --output json)"
jq -e --arg application "$APPLICATION" --arg environment "$ENVIRONMENT" \
  '(.ApplicationName == $application) and (.EnvironmentName == $environment)' \
  <<<"$environment" >/dev/null
echo "$environment" | jq .

stack="$(aws cloudformation describe-stacks \
  --region "$REGION" \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].{StackId:StackId,StackName:StackName,StackStatus:StackStatus,RoleARN:RoleARN,EnableTerminationProtection:EnableTerminationProtection}' \
  --output json)"
jq -e --arg stack_name "$STACK_NAME" --arg stack_arn "$STACK_ARN" \
  '(.StackName == $stack_name) and (.StackId | startswith($stack_arn))' \
  <<<"$stack" >/dev/null
echo "$stack" | jq .

aws cloudformation list-stack-resources \
  --region "$REGION" \
  --stack-name "$STACK_NAME" \
  --query 'StackResourceSummaries[].{LogicalId:LogicalResourceId,PhysicalId:PhysicalResourceId,Type:ResourceType,Status:ResourceStatus}' \
  --output table

aws cloudformation get-template \
  --region "$REGION" \
  --stack-name "$STACK_NAME" \
  --template-stage Processed \
  --query 'TemplateBody.Resources.*.Type' \
  --output text
