#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${CTORM_S3_ROLE_ARN:-}" ]]; then
  echo "CTORM_S3_ROLE_ARN is required" >&2
  exit 1
fi

echo "Refreshing CTORM upload role credentials..." >&2

unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
CREDS_JSON="$(aws sts assume-role \
  --role-arn "${CTORM_S3_ROLE_ARN}" \
  --role-session-name "cumulus-db-md-extract-${CODEBUILD_BUILD_NUMBER:-manual}-$(date +%s)")"

export AWS_ACCESS_KEY_ID="$(echo "${CREDS_JSON}" | jq -r '.Credentials.AccessKeyId')"
export AWS_SECRET_ACCESS_KEY="$(echo "${CREDS_JSON}" | jq -r '.Credentials.SecretAccessKey')"
export AWS_SESSION_TOKEN="$(echo "${CREDS_JSON}" | jq -r '.Credentials.SessionToken')"

aws sts get-caller-identity >&2
