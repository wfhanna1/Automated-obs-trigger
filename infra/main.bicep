// main.bicep — Azure infrastructure for Automated OBS Trigger
//
// Resources deployed:
//   - Storage Account          (Azure Functions runtime storage)
//   - Service Bus Namespace    (Standard tier) + Queue "obs-jobs"
//   - Key Vault                (Standard, RBAC auth)
//   - App Service Plan         (Premium EP1, Linux — gives static outbound IPs)
//   - Function App             (Python 3.11, system-assigned Managed Identity)
//   - Role Assignment          (Key Vault Secrets User → Function App identity)
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
// App Service Plan  (Premium EP1, Linux — enables static outbound IPs)
// ---------------------------------------------------------------------------

resource appPlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: 'obs-scheduler-plan-${nameSuffix}'
  location: location
  kind: 'elastic'
  sku: {
    name: 'EP1'
    tier: 'ElasticPremium'
  }
  properties: {
    reserved: true   // Linux
  }
}

// ---------------------------------------------------------------------------
// Function App
// ---------------------------------------------------------------------------

var storageConnString = 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'

resource funcApp 'Microsoft.Web/sites@2023-01-01' = {
  name: 'obs-scheduler-${nameSuffix}'
  location: location
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: appPlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'Python|3.11'
      appSettings: [
        { name: 'AzureWebJobsStorage',         value: storageConnString }
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME',    value: 'python' }
        { name: 'WEBSITE_RUN_FROM_PACKAGE',    value: '1' }
        { name: 'SERVICE_BUS_CONNECTION',      value: sbAuthRule.listKeys().primaryConnectionString }
        { name: 'KEY_VAULT_URI',               value: keyVault.properties.vaultUri }
        { name: 'GITHUB_RAW_CSV_URL',          value: githubRawCsvUrl }
        { name: 'SERVERS_CONFIG_URL',          value: serversConfigUrl }
      ]
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
// Outputs  (used by deploy-infra.yml to print next steps)
// ---------------------------------------------------------------------------

output functionAppName string = funcApp.name
output functionAppUrl  string = 'https://${funcApp.properties.defaultHostName}'
output keyVaultName    string = keyVault.name
output keyVaultUri     string = keyVault.properties.vaultUri
output serviceBusName  string = sbNamespace.name
output storageName     string = storage.name
