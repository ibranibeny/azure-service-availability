// Azure Service Availability - backend infrastructure (Indonesia Central by default)
//  - Collector Function app (Flex Consumption, timer trigger) runs the Azure CLI on a schedule
//  - API Function app (Flex Consumption, HTTP) validates Microsoft Entra ID tokens and serves the data
//  - Azure Managed Redis holds the snapshot (private endpoint, Entra ID auth, no access keys)
//  - Storage (private endpoints, no shared keys), App Insights (Entra auth), VNet + private DNS
targetScope = 'resourceGroup'

@description('Region for all resources.')
param location string = resourceGroup().location

@description('Short prefix used in resource names.')
@maxLength(6)
param namePrefix string = 'asa'

@description('Microsoft Entra tenant that issues the dashboard users\' tokens.')
param tenantId string = subscription().tenantId

@description('Application (client) ID of the API app registration (token audience).')
param apiClientId string

@description('Application (client) ID of the dashboard single-page app registration (allowed caller).')
param spaClientId string

@description('Comma-separated user domains allowed to read data, e.g. contoso.day.')
param allowedUserDomains string = 'contoso.day'

@description('Browser origins allowed to call the API (CORS).')
param allowedOrigins array = [
  'https://ibranibeny.github.io'
]

@description('NCRONTAB schedule (UTC) of the collector timer. Default: every 6 hours.')
param collectSchedule string = '0 0 */6 * * *'

@description('Azure Managed Redis SKU.')
param redisSku string = 'Balanced_B0'

@description('Azure Managed Redis high availability (replication).')
@allowed([
  'Enabled'
  'Disabled'
])
param redisHighAvailability string = 'Enabled'

@description('Add a NAT gateway for outbound internet traffic from the Function apps subnet.')
param enableNatGateway bool = false

param tags object = {
  app: 'azure-service-availability'
}

var token = toLower(uniqueString(subscription().id, resourceGroup().id, location))
var sfx = substring(token, 0, 6)
var names = {
  law: 'log-${namePrefix}-${sfx}'
  appi: 'appi-${namePrefix}-${sfx}'
  vnet: 'vnet-${namePrefix}-${sfx}'
  nat: 'nat-${namePrefix}-${sfx}'
  pip: 'pip-nat-${namePrefix}-${sfx}'
  storage: 'st${namePrefix}${token}'
  redis: 'redis-${namePrefix}-${sfx}'
  idCollector: 'id-${namePrefix}-collector-${sfx}'
  idApi: 'id-${namePrefix}-api-${sfx}'
  planCollector: 'plan-${namePrefix}-collector-${sfx}'
  planApi: 'plan-${namePrefix}-api-${sfx}'
  funcCollector: 'func-${namePrefix}-collector-${sfx}'
  funcApi: 'func-${namePrefix}-api-${sfx}'
}
var roles = {
  reader: 'acdd72a7-3385-48ef-bd42-f606fba81ae7'
  blobOwner: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
  queueContributor: '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
  tableContributor: '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
  metricsPublisher: '3913510d-42f4-4e42-8a64-420c390055eb'
}
var storageSuffix = environment().suffixes.storage
var storageServices = [
  'blob'
  'queue'
  'table'
]

// ---------------- Monitoring ----------------
resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: names.law
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appi 'Microsoft.Insights/components@2020-02-02' = {
  name: names.appi
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: law.id
    DisableLocalAuth: true
  }
}

// ---------------- Network ----------------
resource pip 'Microsoft.Network/publicIPAddresses@2024-05-01' = if (enableNatGateway) {
  name: names.pip
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource nat 'Microsoft.Network/natGateways@2024-05-01' = if (enableNatGateway) {
  name: names.nat
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    idleTimeoutInMinutes: 10
    publicIpAddresses: [
      {
        id: pip.id
      }
    ]
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: names.vnet
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.62.0.0/24'
      ]
    }
    subnets: [
      {
        name: 'snet-functions'
        properties: {
          addressPrefix: '10.62.0.0/26'
          defaultOutboundAccess: true
          natGateway: enableNatGateway ? {
            id: nat.id
          } : null
          delegations: [
            {
              name: 'flex-consumption'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'snet-private-endpoints'
        properties: {
          addressPrefix: '10.62.0.64/27'
          defaultOutboundAccess: false
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

var funcSubnetId = '${vnet.id}/subnets/snet-functions'
var peSubnetId = '${vnet.id}/subnets/snet-private-endpoints'

resource storageDns 'Microsoft.Network/privateDnsZones@2020-06-01' = [for svc in storageServices: {
  name: 'privatelink.${svc}.${storageSuffix}'
  location: 'global'
  tags: tags
}]

resource storageDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (svc, i) in storageServices: {
  parent: storageDns[i]
  name: 'link-${names.vnet}'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}]

resource redisDns 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.redis.azure.net'
  location: 'global'
  tags: tags
}

resource redisDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: redisDns
  name: 'link-${names.vnet}'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

// ---------------- Identities ----------------
resource idCollector 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: names.idCollector
  location: location
  tags: tags
}

resource idApi 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: names.idApi
  location: location
  tags: tags
}

// ---------------- Storage (Functions host + deployment packages) ----------------
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: names.storage
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource pkgCollector 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'app-package-collector'
}

resource pkgApi 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'app-package-api'
}

resource storagePe 'Microsoft.Network/privateEndpoints@2024-05-01' = [for svc in storageServices: {
  name: 'pe-${names.storage}-${svc}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: peSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'storage-${svc}'
        properties: {
          privateLinkServiceId: storage.id
          groupIds: [
            svc
          ]
        }
      }
    ]
  }
}]

resource storagePeDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = [for (svc, i) in storageServices: {
  parent: storagePe[i]
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: svc
        properties: {
          privateDnsZoneId: storageDns[i].id
        }
      }
    ]
  }
}]

var storageRoles = [
  roles.blobOwner
  roles.queueContributor
  roles.tableContributor
]

resource storageRolesCollector 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for role in storageRoles: {
  name: guid(storage.id, idCollector.id, role)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role)
    principalId: idCollector.properties.principalId
    principalType: 'ServicePrincipal'
  }
}]

resource storageRolesApi 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for role in storageRoles: {
  name: guid(storage.id, idApi.id, role)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role)
    principalId: idApi.properties.principalId
    principalType: 'ServicePrincipal'
  }
}]

resource appiRoleCollector 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(appi.id, idCollector.id, roles.metricsPublisher)
  scope: appi
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.metricsPublisher)
    principalId: idCollector.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource appiRoleApi 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(appi.id, idApi.id, roles.metricsPublisher)
  scope: appi
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.metricsPublisher)
    principalId: idApi.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// The collector reads regions, providers and VM SKUs for the whole subscription.
module collectorReader 'modules/subscription-reader.bicep' = {
  name: 'reader-${sfx}'
  scope: subscription()
  params: {
    principalId: idCollector.properties.principalId
  }
}

// ---------------- Azure Managed Redis ----------------
resource redis 'Microsoft.Cache/redisEnterprise@2025-07-01' = {
  name: names.redis
  location: location
  tags: tags
  sku: {
    name: redisSku
  }
  properties: {
    minimumTlsVersion: '1.2'
    highAvailability: redisHighAvailability
    publicNetworkAccess: 'Disabled'
  }
}

resource redisDb 'Microsoft.Cache/redisEnterprise/databases@2025-07-01' = {
  parent: redis
  name: 'default'
  properties: {
    clientProtocol: 'Encrypted'
    port: 10000
    clusteringPolicy: 'EnterpriseCluster'
    evictionPolicy: 'NoEviction'
    accessKeysAuthentication: 'Disabled'
  }
}

resource redisAccessCollector 'Microsoft.Cache/redisEnterprise/databases/accessPolicyAssignments@2025-07-01' = {
  parent: redisDb
  name: 'collector'
  properties: {
    accessPolicyName: 'default'
    user: {
      objectId: idCollector.properties.principalId
    }
  }
}

resource redisAccessApi 'Microsoft.Cache/redisEnterprise/databases/accessPolicyAssignments@2025-07-01' = {
  parent: redisDb
  name: 'api'
  properties: {
    accessPolicyName: 'default'
    user: {
      objectId: idApi.properties.principalId
    }
  }
  dependsOn: [
    redisAccessCollector
  ]
}

resource redisPe 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-${names.redis}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: peSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'redis'
        properties: {
          privateLinkServiceId: redis.id
          groupIds: [
            'redisEnterprise'
          ]
        }
      }
    ]
  }
}

resource redisPeDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: redisPe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'redis'
        properties: {
          privateDnsZoneId: redisDns.id
        }
      }
    ]
  }
}

// ---------------- Function apps (Flex Consumption) ----------------
var commonSettings = [
  {
    name: 'AzureWebJobsStorage__accountName'
    value: storage.name
  }
  {
    name: 'AzureWebJobsStorage__credential'
    value: 'managedidentity'
  }
  {
    name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
    value: appi.properties.ConnectionString
  }
  {
    name: 'REDIS_HOST'
    value: redis.properties.hostName
  }
  {
    name: 'REDIS_PORT'
    value: '10000'
  }
  {
    name: 'COLLECT_SCHEDULE'
    value: collectSchedule
  }
]

resource planCollector 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: names.planCollector
  location: location
  tags: tags
  kind: 'functionapp'
  sku: {
    tier: 'FlexConsumption'
    name: 'FC1'
  }
  properties: {
    reserved: true
  }
}

resource funcCollector 'Microsoft.Web/sites@2024-04-01' = {
  name: names.funcCollector
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${idCollector.id}': {}
    }
  }
  properties: {
    serverFarmId: planCollector.id
    httpsOnly: true
    virtualNetworkSubnetId: funcSubnetId
    siteConfig: {
      minTlsVersion: '1.2'
      appSettings: concat(commonSettings, [
        {
          name: 'AzureWebJobsStorage__clientId'
          value: idCollector.properties.clientId
        }
        {
          name: 'APPLICATIONINSIGHTS_AUTHENTICATION_STRING'
          value: 'ClientId=${idCollector.properties.clientId};Authorization=AAD'
        }
        {
          name: 'AZURE_CLIENT_ID'
          value: idCollector.properties.clientId
        }
        {
          name: 'AZURE_SUBSCRIPTION_ID'
          value: subscription().subscriptionId
        }
        {
          name: 'REDIS_USER_OBJECT_ID'
          value: idCollector.properties.principalId
        }
        {
          name: 'VM_PARALLELISM'
          value: '8'
        }
      ])
    }
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}${pkgCollector.name}'
          authentication: {
            type: 'UserAssignedIdentity'
            userAssignedIdentityResourceId: idCollector.id
          }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 10
        instanceMemoryMB: 4096
      }
      runtime: {
        name: 'python'
        version: '3.12'
      }
    }
  }
  dependsOn: [
    storageRolesCollector
    storagePeDns
  ]
}

resource planApi 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: names.planApi
  location: location
  tags: tags
  kind: 'functionapp'
  sku: {
    tier: 'FlexConsumption'
    name: 'FC1'
  }
  properties: {
    reserved: true
  }
}

resource funcApi 'Microsoft.Web/sites@2024-04-01' = {
  name: names.funcApi
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${idApi.id}': {}
    }
  }
  properties: {
    serverFarmId: planApi.id
    httpsOnly: true
    virtualNetworkSubnetId: funcSubnetId
    siteConfig: {
      minTlsVersion: '1.2'
      cors: {
        allowedOrigins: allowedOrigins
        supportCredentials: false
      }
      appSettings: concat(commonSettings, [
        {
          name: 'AzureWebJobsStorage__clientId'
          value: idApi.properties.clientId
        }
        {
          name: 'APPLICATIONINSIGHTS_AUTHENTICATION_STRING'
          value: 'ClientId=${idApi.properties.clientId};Authorization=AAD'
        }
        {
          name: 'AZURE_CLIENT_ID'
          value: idApi.properties.clientId
        }
        {
          name: 'REDIS_USER_OBJECT_ID'
          value: idApi.properties.principalId
        }
        {
          name: 'AUTH_TENANT_ID'
          value: tenantId
        }
        {
          name: 'AUTH_API_CLIENT_ID'
          value: apiClientId
        }
        {
          name: 'AUTH_ALLOWED_CLIENT_IDS'
          value: spaClientId
        }
        {
          name: 'AUTH_REQUIRED_SCOPE'
          value: 'Availability.Read'
        }
        {
          name: 'AUTH_ALLOWED_DOMAINS'
          value: allowedUserDomains
        }
        {
          name: 'AUTH_ALLOW_GUESTS'
          value: 'false'
        }
      ])
    }
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}${pkgApi.name}'
          authentication: {
            type: 'UserAssignedIdentity'
            userAssignedIdentityResourceId: idApi.id
          }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 20
        instanceMemoryMB: 2048
      }
      runtime: {
        name: 'python'
        version: '3.12'
      }
    }
  }
  dependsOn: [
    storageRolesApi
    storagePeDns
    // Both apps join snet-functions; integrating them at the same time fails with
    // "Failed to acquire ServiceAssociationLinkLease", so the API app waits for the collector.
    funcCollector
  ]
}

output collectorAppName string = funcCollector.name
output apiAppName string = funcApi.name
output apiBaseUrl string = 'https://${funcApi.properties.defaultHostName}/api'
output redisHost string = redis.properties.hostName
output storageAccountName string = storage.name
output appInsightsName string = appi.name
output collectSchedule string = collectSchedule
