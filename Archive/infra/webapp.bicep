param location string = resourceGroup().location
param appName string = 'azure-cost-optimizer'
param postgresAdminUser string = 'costadmin'
@secure()
param postgresAdminPassword string

// Azure Database for PostgreSQL Flexible Server
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: '${appName}-pg'
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    administratorLogin: postgresAdminUser
    administratorLoginPassword: postgresAdminPassword
    version: '15'
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
  }
}

// App Service Plan (Linux B1)
resource plan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: '${appName}-plan'
  location: location
  kind: 'linux'
  sku: { name: 'B1', tier: 'Basic' }
  properties: { reserved: true }
}

// Web App
resource webApp 'Microsoft.Web/sites@2023-01-01' = {
  name: appName
  location: location
  identity: { type: 'SystemAssigned' }  // Managed Identity
  properties: {
    serverFarmId: plan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      appCommandLine: 'uvicorn app.main:app --host 0.0.0.0 --port 8000'
      appSettings: [
        {
          name: 'DATABASE_URL'
          value: 'postgresql+psycopg2://${postgresAdminUser}:${postgresAdminPassword}@${postgres.properties.fullyQualifiedDomainName}/costdb?sslmode=require'
        }
        {
          name: 'WEBSITE_RUN_FROM_PACKAGE'
          value: '1'
        }
      ]
    }
  }
}

// Role assignment: Cost Management Reader on subscription
output webAppPrincipalId string = webApp.identity.principalId
output webAppUrl string = 'https://${webApp.properties.defaultHostName}'
