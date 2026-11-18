#!/usr/bin/env bash
# Create or update the two Microsoft Entra app registrations (single tenant):
#   API app        - exposes the delegated scope Availability.Read, issues v2 tokens,
#                    pre-authorizes the dashboard so users see no consent prompt for it
#   Dashboard SPA  - single-page app redirect URIs (GitHub Pages + localhost), no secret
# Sourced by deploy.sh; exports API_APP_ID, SPA_APP_ID, SCOPE_ID.
set -euo pipefail

API_NAME="${API_APP_NAME:-Azure Service Availability API}"
SPA_NAME="${SPA_APP_NAME:-Azure Service Availability Dashboard}"
PAGES_URL="${PAGES_URL:-https://ibranibeny.github.io/azure-service-availability/}"
SCOPE_VALUE="Availability.Read"
GRAPH="https://graph.microsoft.com/v1.0"
GRAPH_APP="00000003-0000-0000-c000-000000000000"

app_id_by_name() { az ad app list --display-name "$1" --query "[0].appId" -o tsv; }

API_APP_ID="$(app_id_by_name "$API_NAME")"
if [ -z "$API_APP_ID" ]; then
  API_APP_ID="$(az ad app create --display-name "$API_NAME" --sign-in-audience AzureADMyOrg --query appId -o tsv)"
  echo "Created API app registration $API_APP_ID"
fi
API_OBJ="$(az ad app show --id "$API_APP_ID" --query id -o tsv)"
SCOPE_ID="$(az ad app show --id "$API_APP_ID" --query "api.oauth2PermissionScopes[?value=='$SCOPE_VALUE'].id | [0]" -o tsv)"
[ -n "$SCOPE_ID" ] || SCOPE_ID="$(cat /proc/sys/kernel/random/uuid)"

SPA_APP_ID="$(app_id_by_name "$SPA_NAME")"
if [ -z "$SPA_APP_ID" ]; then
  SPA_APP_ID="$(az ad app create --display-name "$SPA_NAME" --sign-in-audience AzureADMyOrg --query appId -o tsv)"
  echo "Created dashboard app registration $SPA_APP_ID"
fi
SPA_OBJ="$(az ad app show --id "$SPA_APP_ID" --query id -o tsv)"

scope_json() {
  cat <<JSON
{"id":"$SCOPE_ID","value":"$SCOPE_VALUE","type":"User","isEnabled":true,
 "adminConsentDisplayName":"Read Azure service availability",
 "adminConsentDescription":"Allows the dashboard to read the Azure service availability snapshot for the signed-in user.",
 "userConsentDisplayName":"Read Azure service availability",
 "userConsentDescription":"Allows the dashboard to read the Azure service availability snapshot for you."}
JSON
}

# 1) identifier URI, v2 access tokens, delegated scope
cat > /tmp/asa-api-1.json <<JSON
{"identifierUris":["api://$API_APP_ID"],
 "api":{"requestedAccessTokenVersion":2,"oauth2PermissionScopes":[$(scope_json)]}}
JSON
az rest --method PATCH --url "$GRAPH/applications/$API_OBJ" --headers Content-Type=application/json \
  --body @/tmp/asa-api-1.json -o none

# 2) pre-authorize the dashboard for the scope (needs the scope to exist first)
cat > /tmp/asa-api-2.json <<JSON
{"api":{"requestedAccessTokenVersion":2,"oauth2PermissionScopes":[$(scope_json)],
 "preAuthorizedApplications":[{"appId":"$SPA_APP_ID","delegatedPermissionIds":["$SCOPE_ID"]}]}}
JSON
az rest --method PATCH --url "$GRAPH/applications/$API_OBJ" --headers Content-Type=application/json \
  --body @/tmp/asa-api-2.json -o none

# 3) dashboard: SPA redirect URIs and the permissions it asks for
cat > /tmp/asa-spa.json <<JSON
{"spa":{"redirectUris":["$PAGES_URL","http://localhost:8080/"]},
 "requiredResourceAccess":[
  {"resourceAppId":"$API_APP_ID","resourceAccess":[{"id":"$SCOPE_ID","type":"Scope"}]},
  {"resourceAppId":"$GRAPH_APP","resourceAccess":[
    {"id":"37f7f235-527c-4136-accd-4a02d197296e","type":"Scope"},
    {"id":"14dad69e-099b-42c9-810b-d002981feec1","type":"Scope"},
    {"id":"7427e0e9-2fba-42fe-b0c0-848c9e6a8182","type":"Scope"}]}]}
JSON
az rest --method PATCH --url "$GRAPH/applications/$SPA_OBJ" --headers Content-Type=application/json \
  --body @/tmp/asa-spa.json -o none

# 4) service principals (enterprise apps) in this tenant
az ad sp show --id "$API_APP_ID" -o none 2>/dev/null || az ad sp create --id "$API_APP_ID" -o none
az ad sp show --id "$SPA_APP_ID" -o none 2>/dev/null || az ad sp create --id "$SPA_APP_ID" -o none

# 5) admin consent for the sign-in scopes (openid, profile, offline_access) - best effort
for i in 1 2 3; do
  if az ad app permission admin-consent --id "$SPA_APP_ID" -o none 2>/dev/null; then
    echo "Admin consent granted for the dashboard."; break
  fi
  [ "$i" = 3 ] && echo "Admin consent not granted (needs an admin role). Users see a one-time consent prompt."
  sleep 15
done

export API_APP_ID SPA_APP_ID SCOPE_ID
echo "API app: $API_APP_ID | Dashboard app: $SPA_APP_ID | scope: api://$API_APP_ID/$SCOPE_VALUE"
