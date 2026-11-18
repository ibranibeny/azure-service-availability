#!/usr/bin/env bash
# One-command deployment from Azure Cloud Shell (Bash):
#   git clone https://github.com/ibranibeny/azure-service-availability && cd azure-service-availability
#   bash scripts/deploy.sh
set -euo pipefail

export LOCATION="${LOCATION:-indonesiacentral}"
export RG="${RG:-rg-azure-service-availability}"
export PAGES_ORIGIN="${PAGES_ORIGIN:-https://ibranibeny.github.io}"
export PAGES_URL="${PAGES_URL:-https://ibranibeny.github.io/azure-service-availability/}"
export ALLOWED_DOMAINS="${ALLOWED_DOMAINS:-contoso.day}"
export SCHEDULE="${SCHEDULE:-0 0 */6 * * *}"
export REDIS_SKU="${REDIS_SKU:-Balanced_B0}"
export ENABLE_NAT="${ENABLE_NAT:-false}"
export GUEST_ACCESS="${GUEST_ACCESS:-true}"     # read-only guest view without sign-in
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/.deploy"; mkdir -p "$OUT"
step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

step "Signed-in account and subscription"
az account show --query "{subscription:name, id:id, user:user.name}" -o table
TENANT_ID="$(az account show --query tenantId -o tsv)"

step "Resource providers"
for ns in Microsoft.App Microsoft.Web Microsoft.Cache Microsoft.Network Microsoft.Storage \
          Microsoft.Insights Microsoft.OperationalInsights Microsoft.ManagedIdentity; do
  [ "$(az provider show -n "$ns" --query registrationState -o tsv)" = "Registered" ] \
    || { echo "Registering $ns"; az provider register -n "$ns" --wait; }
done

step "Microsoft Entra app registrations (API + dashboard)"
source "$ROOT/scripts/entra-apps.sh"

step "Infrastructure in $LOCATION (Bicep)"
az group create -n "$RG" -l "$LOCATION" --tags app=azure-service-availability -o none
export DEPLOYMENT="asa-$(date -u +%Y%m%d%H%M%S)"
echo "Deployment $DEPLOYMENT (if Cloud Shell disconnects, run: bash scripts/finish-deploy.sh)"
az deployment group create -g "$RG" -n "$DEPLOYMENT" -f "$ROOT/infra/main.bicep" \
  -p location="$LOCATION" apiClientId="$API_APP_ID" spaClientId="$SPA_APP_ID" \
     allowedUserDomains="$ALLOWED_DOMAINS" allowedOrigins="[\"$PAGES_ORIGIN\"]" \
     collectSchedule="$SCHEDULE" redisSku="$REDIS_SKU" enableNatGateway="$ENABLE_NAT" \
     guestReadAccess="$GUEST_ACCESS" \
  --no-wait -o none

# Build, deploy code, first collection and dashboard settings
export API_APP_ID SPA_APP_ID
bash "$ROOT/scripts/finish-deploy.sh"
