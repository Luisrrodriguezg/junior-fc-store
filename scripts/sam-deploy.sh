#!/usr/bin/env bash
# Builds and deploys backend/template.yaml (RDS + Lambdas + API Gateway) with the secrets from
# .secrets/jfc.env, without ever printing them.
#
#   scripts/sam-deploy.sh                      keep the current OpenShift Route host (if any)
#   scripts/sam-deploy.sh <route-host>         point the /boleteria routes at an OpenShift Route
#   scripts/sam-deploy.sh --sin-boleteria      remove the /boleteria routes
set -euo pipefail
cd "$(dirname "$0")/.."

STACK=junior-fc-backend
REGION=us-west-2

[[ -f .secrets/jfc.env ]] || python3 scripts/generar_secretos.py
set -a; source .secrets/jfc.env; set +a

actual=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Parameters[?ParameterKey=='BoleteriaUrl'].ParameterValue" --output text 2>/dev/null || true)
[[ -z "$actual" || "$actual" == "None" ]] && actual="none"

case "${1:-}" in
  --sin-boleteria) boleteria_url="none" ;;
  "")              boleteria_url="$actual" ;;
  *)               boleteria_url="${1#https://}"; boleteria_url="${boleteria_url%%/*}" ;;
esac

cd backend
sam build --cached
# SAM echoes parameter overrides in its summary; drop that line so secrets never reach the terminal.
sam deploy --no-progressbar --parameter-overrides \
  "DbMasterPassword=$DB_MASTER_PASSWORD" \
  "AppDbPassword=$APP_DB_PASSWORD" \
  "GatewaySecret=$GATEWAY_SECRET" \
  "BoleteriaUrl=$boleteria_url" \
  | grep -v -i "parameter overrides" \
  | sed -e "s/$DB_MASTER_PASSWORD/***/g" -e "s/$APP_DB_PASSWORD/***/g" -e "s/$GATEWAY_SECRET/***/g"

aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[].[OutputKey,OutputValue]" --output text
