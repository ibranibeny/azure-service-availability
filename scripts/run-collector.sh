#!/usr/bin/env bash
# Run the scheduled collector now (same timer function), using the Functions admin API.
set -euo pipefail
RG="${RG:-rg-azure-service-availability}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="${COLLECTOR_APP:-$(jq -r .collectorAppName.value "$ROOT/.deploy/outputs.json")}"
# Newer az versions return the raw ARM shape (properties.defaultHostName); older ones flatten it.
HOST="$(az functionapp show -g "$RG" -n "$APP" --query "properties.defaultHostName || defaultHostName" -o tsv)"
[ -n "$HOST" ] || { echo "Could not read the host name of $APP" >&2; exit 1; }
for i in $(seq 1 10); do
  KEY="$(az functionapp keys list -g "$RG" -n "$APP" --query masterKey -o tsv 2>/dev/null || true)"
  [ -n "$KEY" ] && break; sleep 15
done
CODE="$(curl -sS -o /dev/null -w '%{http_code}' -X POST "https://$HOST/admin/functions/collect" \
  -H "x-functions-key: $KEY" -H 'Content-Type: application/json' -d '{"input":""}')"
echo "Collector run requested on $APP (HTTP $CODE; 202 = accepted)."
