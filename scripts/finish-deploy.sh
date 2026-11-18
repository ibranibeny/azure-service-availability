#!/usr/bin/env bash
# Second half of the deployment: waits for the infrastructure deployment, builds and deploys
# both Function apps, runs the first collection and prints the values for docs/config.js.
# deploy.sh calls it automatically. Run it on its own to resume after Cloud Shell disconnects
# part-way through deploy.sh (safe to run more than once):
#   bash scripts/finish-deploy.sh
set -euo pipefail
export RG="${RG:-rg-azure-service-availability}"
export ALLOWED_DOMAINS="${ALLOWED_DOMAINS:-contoso.day}"
export SCHEDULE="${SCHEDULE:-0 0 */6 * * *}"
API_NAME="${API_APP_NAME:-Azure Service Availability API}"
SPA_NAME="${SPA_APP_NAME:-Azure Service Availability Dashboard}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/.deploy"; mkdir -p "$OUT"
step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

step "Build both Function apps (in the background)"
if [ "${SKIP_BUILD:-false}" = "true" ] && [ -s "$OUT/collector.zip" ] && [ -s "$OUT/api.zip" ]; then
  echo "Reusing $OUT/collector.zip and $OUT/api.zip"; B1=""; B2=""
else
  bash "$ROOT/scripts/build.sh" collector "$OUT/collector.zip" > "$OUT/build-collector.log" 2>&1 & B1=$!
  bash "$ROOT/scripts/build.sh" api "$OUT/api.zip" > "$OUT/build-api.log" 2>&1 & B2=$!
fi

step "Infrastructure deployment in $RG"
DEPLOYMENT="${DEPLOYMENT:-$(az deployment group list -g "$RG" \
  --query "sort_by([?starts_with(name,'asa-')], &name)[-1].name" -o tsv)}"
[ -n "$DEPLOYMENT" ] || { echo "No deployment found in $RG. Run scripts/deploy.sh first." >&2; exit 1; }
while :; do
  STATE="$(az deployment group show -g "$RG" -n "$DEPLOYMENT" --query properties.provisioningState -o tsv 2>/dev/null || echo Pending)"
  echo "$(date -u +%H:%M:%S) UTC  $DEPLOYMENT  $STATE"
  case "$STATE" in
    Succeeded) break ;;
    Failed|Canceled)
      az deployment operation group list -g "$RG" -n "$DEPLOYMENT" \
        --query "[?properties.provisioningState=='Failed'].{resource:properties.targetResource.resourceName, error:properties.statusMessage.error}" -o json
      exit 1 ;;
  esac
  sleep 30
done
az deployment group show -g "$RG" -n "$DEPLOYMENT" --query properties.outputs -o json > "$OUT/outputs.json"
COLLECTOR="$(jq -r .collectorAppName.value "$OUT/outputs.json")"
API="$(jq -r .apiAppName.value "$OUT/outputs.json")"
API_BASE="$(jq -r .apiBaseUrl.value "$OUT/outputs.json")"
TENANT_ID="$(az account show --query tenantId -o tsv)"
API_APP_ID="${API_APP_ID:-$(az ad app list --display-name "$API_NAME" --query "[0].appId" -o tsv)}"
SPA_APP_ID="${SPA_APP_ID:-$(az ad app list --display-name "$SPA_NAME" --query "[0].appId" -o tsv)}"

step "Deploy the Function app code"
for pid in ${B1:-} ${B2:-}; do
  wait "$pid" || { tail -n 30 "$OUT"/build-*.log; echo "Build failed." >&2; exit 1; }
done
tail -qn 1 "$OUT"/build-*.log 2>/dev/null || true
deploy_zip() {
  local app="$1" zip="$2" i
  for i in 1 2 3; do
    az functionapp deployment source config-zip -g "$RG" -n "$app" --src "$zip" --build-remote false -o none \
      && { echo "Deployed $zip to $app"; return 0; }
    echo "Retrying deployment to $app in 30 s"; sleep 30
  done
  return 1
}
deploy_zip "$COLLECTOR" "$OUT/collector.zip"
deploy_zip "$API" "$OUT/api.zip"

step "First collection (the timer then runs it automatically: $SCHEDULE UTC)"
COLLECTOR_APP="$COLLECTOR" bash "$ROOT/scripts/run-collector.sh"

step "Dashboard settings for docs/config.js"
cat > "$OUT/config.js" <<JS
window.ASA_CONFIG = {
  tenantId: "$TENANT_ID",
  clientId: "$SPA_APP_ID",
  apiScope: "api://$API_APP_ID/Availability.Read",
  apiBase: "$API_BASE",
  domainHint: "${ALLOWED_DOMAINS%%,*}"
};
JS
cat "$OUT/config.js"
echo
echo "Collector: $COLLECTOR   API: $API_BASE"
echo "Health check: curl -s $API_BASE/health"
