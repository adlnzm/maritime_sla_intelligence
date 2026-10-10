targetScope = 'resourceGroup'

@description('Lowercase short deployment prefix, globally unique storage names are derived.')
@maxLength(10)
param prefix string = 'maritime'
param location string = resourceGroup().location
@description('Prebuilt public or accessible container image, preferably pinned by digest.')
param apiImage string
param tenantId string = tenant().tenantId
@description('Entra application audience. Register Maritime.Reader and Maritime.Operator app roles.')
param apiAudience string
@description('Existing Azure OpenAI resource name in this resource group.')
param openAIAccountName string
param openAIDeployment string
param computeSku string = 'Standard_DS3_v2'

var suffix = uniqueString(resourceGroup().id)
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${prefix}-logs'

  location: location

  properties: {
    retentionInDays: 30
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${prefix}-insights'

  location: location

  kind: 'web'

  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: '${prefix}${suffix}'

  location: location

  sku: {
    name: 'Standard_LRS'
  }

  kind: 'StorageV2'

  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage

  name: 'default'
}

resource serving 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobs

  name: 'maritime-serving'

  properties: {
    publicAccess: 'None'
  }
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: '${prefix}-${suffix}'

  location: location

  properties: {
    tenantId: tenantId

    sku: {
      family: 'A'
      name: 'standard'
    }

    enableRbacAuthorization: true

    enableSoftDelete: true

    enablePurgeProtection: true

    softDeleteRetentionInDays: 90

    accessPolicies: []
  }
}

resource ml 'Microsoft.MachineLearningServices/workspaces@2024-04-01' = {
  name: '${prefix}-ml'

  location: location

  identity: {
    type: 'SystemAssigned'
  }

  properties: {
    friendlyName: 'Maritime ML'
    storageAccount: storage.id
    keyVault: vault.id
    applicationInsights: insights.id
  }
}

resource compute 'Microsoft.MachineLearningServices/workspaces/computes@2024-04-01' = {
  parent: ml

  name: 'maritime-cpu'

  location: location

  properties: {
    computeType: 'AmlCompute'

    properties: {
      vmSize: computeSku
      vmPriority: 'Dedicated'
      scaleSettings: {
        minNodeCount: 0
        maxNodeCount: 2
        nodeIdleTimeBeforeScaleDown: 'PT5M'
      }
    }
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${prefix}-api-identity'

  location: location
}

resource blobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(serving.id, identity.id, 'blob-reader')

  scope: serving

  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
    )
  }
}

resource vaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, identity.id, 'secrets-user')

  scope: vault

  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '4633458b-17de-408a-b874-0445c86b69e6'
    )
  }
}

resource openai 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = {
  name: openAIAccountName
}

resource openaiRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openai.id, identity.id, 'openai-user')

  scope: openai

  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
    )
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${prefix}-environment'

  location: location

  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-api'

  location: location

  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }

  properties: {
    managedEnvironmentId: environment.id

    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        allowInsecure: false
        transport: 'auto'
      }
    }

    template: {
      scale: {
        minReplicas: 1
        maxReplicas: 2
      }

      containers: [
        {
          name: 'api'

          image: apiImage

          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }

          env: [
            {
              name: 'MARITIME_AUTH_MODE'
              value: 'entra'
            }

            {
              name: 'AZURE_TENANT_ID'
              value: tenantId
            }

            {
              name: 'AZURE_API_AUDIENCE'
              value: apiAudience
            }

            {
              name: 'AZURE_CLIENT_ID'
              value: identity.properties.clientId
            }

            {
              name: 'AZURE_STORAGE_ACCOUNT_URL'
              value: storage.properties.primaryEndpoints.blob
            }

            {
              name: 'MARITIME_STORAGE_BACKEND'
              value: 'azure_blob'
            }

            {
              name: 'AZURE_KEY_VAULT_URL'
              value: vault.properties.vaultUri
            }

            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: openai.properties.endpoint
            }

            {
              name: 'AZURE_OPENAI_DEPLOYMENT'
              value: openAIDeployment
            }

            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: insights.properties.ConnectionString
            }
          ]

          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }

              initialDelaySeconds: 20
              periodSeconds: 30
            }
          ]
        }
      ]
    }
  }
}

output mlWorkspace string = ml.name
output apiUrl string = 'https://${app.properties.configuration.ingress.fqdn}'
output storageUrl string = storage.properties.primaryEndpoints.blob
output keyVaultUrl string = vault.properties.vaultUri

resource audit 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobs
  name: 'maritime-audit'
  properties: { publicAccess: 'None' }
}
resource auditRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(audit.id, identity.id, 'audit-contributor')
  scope: audit
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  }
}
resource mlStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, ml.id, 'ml-storage')
  scope: storage
  properties: {
    principalId: ml.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  }
}
resource mlVaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, ml.id, 'ml-secrets')
  scope: vault
  properties: {
    principalId: ml.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7')
  }
}
