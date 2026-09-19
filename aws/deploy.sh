#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

for cmd in aws sam python3 curl; do
  require_cmd "$cmd"
done

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "AWS CLI is not authenticated." >&2
  exit 1
fi

export AWS_PAGER=""

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
if [[ -z "$REGION" ]]; then
  REGION="$(aws configure get region 2>/dev/null || true)"
fi
REGION="${REGION:-ap-southeast-2}"
STACK_NAME="${STACK_NAME:-roofgrid-api}"
SECRET_NAME="${SECRET_NAME:-roofgrid/config}"
ALLOWED_ORIGIN="${ALLOWED_ORIGIN:-*}"
AI_MODEL="${AI_MODEL:-openai.gpt-oss-120b-1:0}"
AI_DAILY_REQUEST_LIMIT="${AI_DAILY_REQUEST_LIMIT:-100}"
AI_THROTTLE_RATE="${AI_THROTTLE_RATE:-0.5}"
AI_THROTTLE_BURST_LIMIT="${AI_THROTTLE_BURST_LIMIT:-3}"

echo "AWS region: $REGION"
echo "CloudFormation stack: $STACK_NAME"
echo "Secrets Manager secret: $SECRET_NAME"
echo "Bedrock model: $AI_MODEL"
echo "AI daily request cap: $AI_DAILY_REQUEST_LIMIT"
echo "AI throttle: $AI_THROTTLE_RATE req/s, burst $AI_THROTTLE_BURST_LIMIT"
echo "Allowed browser origin: $ALLOWED_ORIGIN"
echo

SECRET_EXISTS=false
if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --region "$REGION" >/dev/null 2>&1; then
  SECRET_EXISTS=true
fi

if [[ -z "${CONTACT_EMAIL:-}" && "$SECRET_EXISTS" == "true" ]]; then
  CONTACT_EMAIL="$(aws secretsmanager get-secret-value     --secret-id "$SECRET_NAME"     --region "$REGION"     --query SecretString     --output text | python3 -c 'import json,sys; print(json.load(sys.stdin).get("CONTACT_EMAIL",""))' 2>/dev/null || true)"
fi

if [[ -z "${CONTACT_EMAIL:-}" ]]; then
  read -r -p "Contact form recipient email: " CONTACT_EMAIL
fi

if [[ -z "$CONTACT_EMAIL" ]]; then
  echo "CONTACT_EMAIL is required." >&2
  exit 1
fi

export CONTACT_EMAIL

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

SECRET_FILE="$TMP_DIR/roofgrid-secret.json"
python3 - "$SECRET_FILE" <<'PY'
import json
import os
import sys

payload = {
    "CONTACT_EMAIL": os.environ["CONTACT_EMAIL"],
}

with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(payload, handle)
PY
chmod 600 "$SECRET_FILE"

if [[ "$SECRET_EXISTS" == "true" ]]; then
  echo "Updating existing Secrets Manager secret..."
  aws secretsmanager put-secret-value     --secret-id "$SECRET_NAME"     --secret-string "file://$SECRET_FILE"     --region "$REGION" >/dev/null
  SECRET_ARN="$(aws secretsmanager describe-secret     --secret-id "$SECRET_NAME"     --region "$REGION"     --query ARN     --output text)"
else
  echo "Creating Secrets Manager secret..."
  SECRET_ARN="$(aws secretsmanager create-secret     --name "$SECRET_NAME"     --secret-string "file://$SECRET_FILE"     --region "$REGION"     --query ARN     --output text)"
fi

echo "Building Lambda package..."
sam build --template-file template.yaml

echo "Deploying API Gateway + Lambda + Bedrock permissions..."
sam deploy   --template-file .aws-sam/build/template.yaml   --stack-name "$STACK_NAME"   --region "$REGION"   --capabilities CAPABILITY_IAM   --resolve-s3   --no-confirm-changeset   --no-fail-on-empty-changeset   --parameter-overrides     "RoofGridSecretArn=$SECRET_ARN"     "AllowedOrigin=$ALLOWED_ORIGIN"     "AiModel=$AI_MODEL"     "AiDailyRequestLimit=$AI_DAILY_REQUEST_LIMIT"     "AiThrottleRate=$AI_THROTTLE_RATE"     "AiThrottleBurstLimit=$AI_THROTTLE_BURST_LIMIT"

API_URL="$(aws cloudformation describe-stacks   --stack-name "$STACK_NAME"   --region "$REGION"   --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue | [0]"   --output text)"

if [[ -z "$API_URL" || "$API_URL" == "None" ]]; then
  echo "Deployment completed, but ApiUrl could not be read from the stack outputs." >&2
  exit 1
fi

echo
echo "Testing backend health..."
curl --fail --silent --show-error "$API_URL/api/health"
echo
echo

if [[ -z "${AMPLIFY_APP_ID:-}" ]]; then
  read -r -p "Amplify app ID (optional; press Enter to skip automatic /api rewrite): " AMPLIFY_APP_ID
fi

if [[ -n "${AMPLIFY_APP_ID:-}" ]]; then
  EXISTING_RULES="$TMP_DIR/existing-rules.json"
  MERGED_RULES="$TMP_DIR/merged-rules.json"

  aws amplify get-app     --app-id "$AMPLIFY_APP_ID"     --region "$REGION"     --query "app.customRules"     --output json > "$EXISTING_RULES"

  API_URL="$API_URL" python3 - "$EXISTING_RULES" "$MERGED_RULES" <<'PY'
import json
import os
import sys

source_path, target_path = sys.argv[1:3]
with open(source_path, "r", encoding="utf-8") as handle:
    current = json.load(handle) or []

current = [rule for rule in current if rule.get("source") != "/api/<*>"]
api_url = os.environ["API_URL"].rstrip("/")
current.insert(0, {
    "source": "/api/<*>",
    "target": f"{api_url}/api/<*>",
    "status": "200",
})

with open(target_path, "w", encoding="utf-8") as handle:
    json.dump(current, handle)
PY

  echo "Updating Amplify /api rewrite while preserving existing rules..."
  aws amplify update-app     --app-id "$AMPLIFY_APP_ID"     --region "$REGION"     --custom-rules "file://$MERGED_RULES" >/dev/null

  echo "Amplify rewrite configured."
else
  echo "Amplify rewrite not changed."
  echo "Add this as the first Amplify rewrite rule:"
  echo "  Source: /api/<*>"
  echo "  Target: $API_URL/api/<*>"
  echo "  Status: 200"
fi

echo
echo "RoofGrid AWS backend is live:"
echo "  API:    $API_URL"
echo "  Health: $API_URL/api/health"
echo "  AI:     Amazon Bedrock ($AI_MODEL)"
echo "  Limit:  $AI_DAILY_REQUEST_LIMIT AI requests/day, $AI_THROTTLE_RATE req/s, burst $AI_THROTTLE_BURST_LIMIT"
echo
if [[ "$ALLOWED_ORIGIN" == "*" ]]; then
  echo "Production hardening: rerun with ALLOWED_ORIGIN=https://YOUR_AMPLIFY_DOMAIN to restrict direct browser API access."
fi
echo "If this is the first FormSubmit message for CONTACT_EMAIL, confirm FormSubmit's activation email."
