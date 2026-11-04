#!/usr/bin/env bash
# RDS bills per hour while running: stop it whenever you're not developing or presenting.
#   scripts/rds.sh status | start | stop
# A stopped instance restarts by itself after 7 days (AWS rule) — check status before leaving it.
set -euo pipefail
DB=jfc-mysql
REGION=us-west-2

estado() {
  aws rds describe-db-instances --db-instance-identifier "$DB" --region "$REGION" \
    --query "DBInstances[0].DBInstanceStatus" --output text
}

case "${1:-status}" in
  status) echo "$DB: $(estado)" ;;
  start)
    aws rds start-db-instance --db-instance-identifier "$DB" --region "$REGION" >/dev/null
    echo "Arrancando $DB (tarda ~5 min)..."
    aws rds wait db-instance-available --db-instance-identifier "$DB" --region "$REGION"
    echo "$DB: $(estado)" ;;
  stop)
    aws rds stop-db-instance --db-instance-identifier "$DB" --region "$REGION" >/dev/null
    echo "Deteniendo $DB. Estado: $(estado)" ;;
  *) echo "uso: $0 status|start|stop" >&2; exit 1 ;;
esac
