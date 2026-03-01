// main.bicep — Azure infrastructure for Automated OBS Trigger
//
// Resources deployed:
//   - Storage Account          (Azure Functions runtime storage)
//   - Storage Blob Container   (Flex Consumption deployment packages)
//   - Service Bus Namespace    (Standard tier) + Queue "obs-jobs"
//   - Key Vault                (Standard, RBAC auth)
//   - Log Analytics Workspace  (backing store for Application Insights)
//   - Application Insights     (workspace-based; captures logs, traces, exceptions)
//   - App Service Plan         (Flex Consumption FC1, Linux)
//   - Function App             (Python 3.11, system-assigned Managed Identity)
//   - Role Assignment          (Key Vault Secrets User → Function App identity)
//   - Role Assignment          (Storage Blob Data Contributor → Function App identity)
//
// Deploy via GitHub Actions (see .github/workflows/deploy-infra.yml)
// or locally:
//   az deployment group create \
//     --resource-group obs-scheduler-rg \
//     --template-file infra/main.bicep \
//     --parameters githubRawCsvUrl=<url> serversConfigUrl=<url>

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Short suffix appended to globally-unique resource names. Defaults to a hash of the resource group ID.')
param nameSuffix string = uniqueString(resourceGroup().id)

@description('GitHub raw URL for schedules/current_week.csv, e.g. https://raw.githubusercontent.com/org/repo/main/schedules/current_week.csv')
param githubRawCsvUrl string = 'REPLACE_WITH_GITHUB_RAW_CSV_URL'

@description('GitHub raw URL for config/servers.yaml, e.g. https://raw.githubusercontent.com/org/repo/main/config/servers.yaml')
param serversConfigUrl string = 'REPLACE_WITH_GITHUB_RAW_SERVERS_URL'

// ---------------------------------------------------------------------------
// Storage Account  (required by Azure Functions runtime)
// ---------------------------------------------------------------------------

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: 'obsstore${nameSuffix}'
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

// Blob container required by Flex Consumption for deployment packages
resource deployContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  name: '${storage.name}/default/deployments'
  properties: { publicAccess: 'None' }
}

// ---------------------------------------------------------------------------
// Service Bus Namespace + Queue
// ---------------------------------------------------------------------------

resource sbNamespace 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: 'obs-scheduler-${nameSuffix}'
  location: location
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
}

// Dedicated auth rule with Listen+Send+Manage for the Function App
resource sbAuthRule 'Microsoft.ServiceBus/namespaces/authorizationRules@2022-10-01-preview' = {
  parent: sbNamespace
  name: 'obs-functions'
  properties: {
    rights: [ 'Listen', 'Send', 'Manage' ]
  }
}

// "obs-jobs" queue — messages held until scheduled_enqueue_time_utc
resource sbQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: sbNamespace
  name: 'obs-jobs'
  properties: {
    lockDuration: 'PT5M'          // 5-minute processing lock
    maxDeliveryCount: 3           // dead-letter after 3 failed attempts
    defaultMessageTimeToLive: 'P7D'
    requiresSession: false
  }
}

// ---------------------------------------------------------------------------
// Key Vault  (stores SSH keys and OBS WebSocket passwords per server)
// ---------------------------------------------------------------------------

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'obs-kv-${nameSuffix}'
  location: location
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true    // RBAC mode — no legacy access policies
    softDeleteRetentionInDays: 7
    enableSoftDelete: true
  }
}

// ---------------------------------------------------------------------------
// Log Analytics Workspace  (backing store for App Insights)
// ---------------------------------------------------------------------------

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'obs-scheduler-logs-${nameSuffix}'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ---------------------------------------------------------------------------
// Application Insights  (workspace-based; classic mode is deprecated)
// ---------------------------------------------------------------------------

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'obs-scheduler-ai-${nameSuffix}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

// ---------------------------------------------------------------------------
// App Service Plan  (Flex Consumption FC1, Linux)
// ---------------------------------------------------------------------------

resource appPlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: 'obs-scheduler-plan-${nameSuffix}'
  location: location
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  properties: {
    reserved: true   // Linux
  }
}

// ---------------------------------------------------------------------------
// Function App
// ---------------------------------------------------------------------------

resource funcApp 'Microsoft.Web/sites@2023-12-01' = {
  name: 'obs-scheduler-${nameSuffix}'
  location: location
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: appPlan.id
    httpsOnly: true
    siteConfig: {
      appSettings: [
        // Flex Consumption uses identity-based host storage — no connection string
        { name: 'AzureWebJobsStorage__accountName', value: storage.name }
        { name: 'FUNCTIONS_EXTENSION_VERSION',      value: '~4' }
        // FUNCTIONS_WORKER_RUNTIME is not allowed; runtime is set in functionAppConfig
        { name: 'SERVICE_BUS_CONNECTION',           value: sbAuthRule.listKeys().primaryConnectionString }
        { name: 'KEY_VAULT_URI',                    value: keyVault.properties.vaultUri }
        { name: 'GITHUB_RAW_CSV_URL',               value: githubRawCsvUrl }
        { name: 'SERVERS_CONFIG_URL',               value: serversConfigUrl }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
      ]
    }
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}deployments'
          authentication: { type: 'SystemAssignedIdentity' }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 10
        instanceMemoryMB: 2048
      }
      runtime: {
        name: 'python'
        version: '3.11'
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Role Assignment: Key Vault Secrets User → Function App Managed Identity
// ---------------------------------------------------------------------------

// Built-in role: Key Vault Secrets User (read secrets)
var kvSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

resource kvRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, funcApp.id, kvSecretsUserRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvSecretsUserRoleId)
    principalId: funcApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------------------
// Role Assignment: Storage Blob Data Contributor → Function App Managed Identity
// (required for Flex Consumption identity-based host storage)
// ---------------------------------------------------------------------------

var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

resource storageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, funcApp.id, storageBlobDataContributorRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
    principalId: funcApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------------------
// Outputs  (used by deploy-infra.yml to print next steps)
// ---------------------------------------------------------------------------

output functionAppName  string = funcApp.name
output functionAppUrl   string = 'https://${funcApp.properties.defaultHostName}'
output keyVaultName     string = keyVault.name
output keyVaultUri      string = keyVault.properties.vaultUri
output serviceBusName   string = sbNamespace.name
output storageName      string = storage.name
output appInsightsName  string = appInsights.name
output logAnalyticsName string = logAnalytics.name
