#!/usr/bin/env bash
# What the Functions storage account holds and how it is locked down.
# Uses Azure Resource Manager (the management plane) only, so it works from Cloud Shell even though
# the storage account has public network access disabled. It lists names and settings; it never
# reads what is inside blobs, queues or tables.
#   bash scripts/inspect-storage.sh             # storage report
#   bash scripts/inspect-storage.sh --timings   # plus deployment history and the slowest resources
set -euo pipefail
RG="${RG:-rg-azure-service-availability}"
ST="${STORAGE:-$(az storage account list -g "$RG" --query "[0].name" -o tsv)}"
ARM="/subscriptions/{subscriptionId}/resourceGroups/$RG/providers/Microsoft.Storage/storageAccounts/$ST"
h() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }

h "Storage account $ST"
az storage account show -n "$ST" -g "$RG" --query "{kind:kind, sku:sku.name, publicNetworkAccess:publicNetworkAccess, allowSharedKeyAccess:allowSharedKeyAccess, defaultToOAuthAuthentication:defaultToOAuthAuthentication, allowBlobPublicAccess:allowBlobPublicAccess, minimumTlsVersion:minimumTlsVersion}" -o yaml

h "Private endpoints"
az network private-endpoint list -g "$RG" --query "[?contains(name, '$ST')].{endpoint:name, service:privateLinkServiceConnections[0].groupIds[0], state:privateLinkServiceConnections[0].privateLinkServiceConnectionState.status}" -o table

h "Blob containers"
az storage container-rm list --storage-account "$ST" -g "$RG" --query "[].{container:name, lastModified:lastModifiedTime}" -o table
h "Queues"
az rest --url "$ARM/queueServices/default/queues?api-version=2023-05-01" --query "value[].name" -o tsv
h "Tables"
az rest --url "$ARM/tableServices/default/tables?api-version=2023-05-01" --query "value[].name" -o tsv

h "Role assignments on the storage account"
SID="$(az storage account show -n "$ST" -g "$RG" --query id -o tsv)"
declare -A NAME=()
while IFS=$'\t' read -r n p; do NAME[$p]="$n"; done < <(az identity list -g "$RG" --query "[].[name, principalId]" -o tsv)
az role assignment list --scope "$SID" --query "[].[principalId, roleDefinitionName]" -o tsv \
  | while IFS=$'\t' read -r p r; do printf '%-34s %s\n' "${NAME[$p]:-$p}" "$r"; done | sort

for APP in $(az functionapp list -g "$RG" --query "[].name" -o tsv); do
  h "$APP: host storage settings and deployment package"
  az functionapp config appsettings list -g "$RG" -n "$APP" --query "[?starts_with(name, 'AzureWebJobsStorage')].{setting:name, value:value}" -o table
  az functionapp show -g "$RG" -n "$APP" \
    --query "(properties.functionAppConfig || functionAppConfig).deployment.storage.{type:type, container:value, authentication:authentication.type}" -o yaml
done

if [ "${1:-}" = "--timings" ]; then
  h "Deployments in $RG"
  az deployment group list -g "$RG" --query "sort_by(@, &properties.timestamp)[].{name:name, state:properties.provisioningState, finishedUtc:properties.timestamp, duration:properties.duration}" -o table
  for D in $(az deployment group list -g "$RG" --query "sort_by(@, &properties.timestamp)[].name" -o tsv); do
    h "Slowest resources in $D"
    az deployment operation group list -g "$RG" -n "$D" -o json | jq -r '
      def num: if . == null or . == "" then 0 else tonumber end;
      def secs: capture("PT((?<h>[0-9.]+)H)?((?<m>[0-9.]+)M)?((?<s>[0-9.]+)S)?")
        | ((.h | num) * 3600 + (.m | num) * 60 + (.s | num));
      def pad(w): tostring | . + (" " * ([w - length, 1] | max));
      [ .[] | select(.properties.targetResource.resourceType != null)
        | { t: (.properties.targetResource.resourceType | split("/") | .[1:] | join("/")),
            n: (.properties.targetResource.resourceName | split("/") | last),
            s: .properties.provisioningState,
            d: (.properties.duration | secs) } ]
      | sort_by(-.d) | .[:6][] | "\((.d | floor | tostring) + "s" | pad(7))\(.s | pad(11))\(.t | pad(46))\(.n)"'
  done
fi
