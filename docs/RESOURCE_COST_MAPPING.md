# Resource cost driver mapping

Maps each resource type to inventory **properties** and Azure Monitor **metrics** that drive cost recommendations.

Generated from `app/resource_cost_mapping.py`. Do not edit by hand.

## Azure Data Explorer (`analytics/adx`)
ARM type: `Microsoft.Kusto/clusters`
Synced properties: `provisioningState`, `state`, `sku`

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `ingestion_bytes` | IngestionVolumeInMB | cost | — | — |

---

## Azure Databricks (`analytics/databricks`)
ARM type: `Microsoft.Databricks/workspaces`
Synced properties: `provisioningState`, `parameters`

---

## Azure ML workspace (`analytics/mlworkspace`)
ARM type: `Microsoft.MachineLearningServices/workspaces`
Synced properties: `provisioningState`, `discoveryUrl`

---

## Azure Synapse (`analytics/synapse`)
ARM type: `Microsoft.Synapse/workspaces`
Synced properties: `provisioningState`, `settings`

---

## App Service plan (`appservice/plan`)
ARM type: `Microsoft.Web/serverFarms`
Synced properties: `numberOfSites`, `reserved`, `status`, `maximumNumberOfWorkers`, `targetWorkerCount`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `app_count` | Hosted app count | `computed:app_count` | PLAN_EMPTY, PLAN_UNDERUTILIZED |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `cpu_pct` | CpuPercentage | both | PLAN_UNDERUTILIZED, APP_SERVICE_PLAN_EXTENDED | Low SQL CPU supports serverless or lower tier migration. |
| `memory_pct` | MemoryPercentage | both | PLAN_UNDERUTILIZED, APP_SERVICE_PLAN_EXTENDED | Low Redis memory supports smaller cache SKU. |

---

## App Service (`appservice/webapp`)
ARM type: `Microsoft.Web/sites`
Synced properties: `kind`, `state`, `alwaysOn`, `httpsOnly`, `clientAffinityEnabled`, `serverFarmId`, `siteConfig`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `state` | App state | `props:state` | APP_IDLE, APP_ALWAYS_ON_OFF |
| `alwaysOn` | Always On | `props:alwaysOn` | APP_ALWAYS_ON_OFF |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `cpu_time_sec` | CpuTime | both | APP_IDLE, WEBAPP_STOPPED_EXTENDED | — |
| `avg_memory_bytes` | AverageMemoryWorkingSet | cost | APP_IDLE, WEBAPP_ALWAYS_ON_EXTENDED | — |
| `request_count` | Requests | cost | APP_IDLE, WEBAPP_STOPPED_EXTENDED | Low request volume supports plan downgrade or resource removal. |

---

## Recovery Services vault (`backup/recoveryvault`)
ARM type: `Microsoft.RecoveryServices/vaults`
Synced properties: `provisioningState`, `sku`

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `backup_health_events` | BackupHealthEvent | both | — | — |

---

## Managed disk (`compute/disk`)
ARM type: `Microsoft.Compute/disks`
Synced properties: `diskSizeGB`, `diskState`, `diskIOPSReadWrite`, `diskMBpsReadWrite`, `managedBy`, `encryption`, `provisioningState`, `timeCreated`, …

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `disk_state` | Disk state | `props:diskState` | DISK_UNATTACHED, DISK_OVERSIZE, DISK_UNUSED_EXTENDED, DISK_UNDERPROVISIONED |
| `size_gb` | Disk size (GB) | `props:diskSizeGB` | DISK_UNATTACHED, DISK_OVERSIZE, DISK_UNDERPROVISIONED |
| `provisioned_iops` | Provisioned IOPS | `props:diskIOPSReadWrite` | DISK_OVERSIZE_EXTENDED, DISK_UNDERPROVISIONED |
| `provisioned_mbps` | Provisioned throughput (MB/s) | `props:diskMBpsReadWrite` | DISK_OVERSIZE_EXTENDED, DISK_UNDERPROVISIONED |
| `sku` | SKU | `row:sku` | DISK_UNATTACHED, DISK_OVERSIZE, DISK_OVERSIZE_EXTENDED, DISK_UNDERPROVISIONED |
| `managed_by` | Attached to | `props:managedBy` | DISK_UNATTACHED |
| `last_managed_by` | Last attached to | `props:lastManagedBy` | DISK_UNUSED_EXTENDED |
| `time_created` | Created | `props:timeCreated` | DISK_UNUSED_EXTENDED |
| `last_ownership_update` | Last ownership update time | `props:lastOwnershipUpdateTime` | DISK_UNUSED_EXTENDED |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `disk_read_bps` | Composite Disk Read Bytes/sec | cost | DISK_OVERSIZE, DISK_UNUSED_EXTENDED, DISK_OVERSIZE_EXTENDED | Near-zero I/O on premium disks enables tier downgrade savings. |
| `disk_write_bps` | Composite Disk Write Bytes/sec | cost | DISK_OVERSIZE, DISK_UNUSED_EXTENDED, DISK_OVERSIZE_EXTENDED | Near-zero I/O on premium disks enables tier downgrade savings. |

---

## Disk snapshot (`compute/snapshot`)
ARM type: `Microsoft.Compute/snapshots`
Synced properties: `diskSizeGB`, `diskState`, `provisioningState`, `timeCreated`, `creationData`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `size_gb` | Snapshot size (GB) | `props:diskSizeGB` | SNAPSHOT_OLD, SNAPSHOT_RETENTION_EXTENDED |
| `disk_state` | Snapshot state | `props:diskState` | SNAPSHOT_OLD, SNAPSHOT_RETENTION_EXTENDED |
| `provisioning_state` | Provisioning state | `props:provisioningState` | SNAPSHOT_RETENTION_EXTENDED |
| `sku` | SKU | `row:sku` | SNAPSHOT_OLD, SNAPSHOT_RETENTION_EXTENDED |
| `time_created` | Created | `props:timeCreated` | SNAPSHOT_OLD, SNAPSHOT_RETENTION_EXTENDED |
| `age_days` | Age (days) | `computed:snapshot_age_days` | SNAPSHOT_OLD, SNAPSHOT_RETENTION_EXTENDED |
| `source_disk_id` | Source disk | `props:creationData.sourceResourceId` | SNAPSHOT_RETENTION_EXTENDED |
| `incremental` | Incremental snapshot | `props:creationData.incremental` | SNAPSHOT_RETENTION_EXTENDED |

---

## Virtual machine (`compute/vm`)
ARM type: `Microsoft.Compute/virtualMachines`
Synced properties: `hardwareProfile`, `storageProfile`, `osProfile`, `provisioningState`, `powerState`, `instanceView`, `timeCreated`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `vm_size` | VM size | `props:hardwareProfile.vmSize` | VM_IDLE, VM_OVERSIZE, VM_NO_RESERVED, VM_RIGHTSIZE_FAMILY |
| `power_state` | Power state | `computed:power_state` | VM_IDLE, VM_STOPPED_DEALLOCATED, VM_STOPPED_BILLING_EXTENDED, VM_NO_RESERVED |
| `time_created` | Time created | `props:timeCreated` | VM_COMMITMENT_CANDIDATE |
| `environment` | Environment tag | `tag:Environment` | SPOT_OPPORTUNITY, VM_MISSING_GOVERNANCE_TAGS |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `avg_cpu_pct` | Percentage CPU | both | VM_IDLE, VM_OVERSIZE, VM_UNDERUTILIZED_EXTENDED, VM_RIGHTSIZE_FAMILY, VM_SKU_SIZING_EXTENDED | Low CPU enables idle VM removal and rightsizing savings (up to 90% MTD). |
| `avg_available_memory_bytes` | Available Memory Bytes | cost | VM_OVERSIZE, VM_SKU_SIZING_EXTENDED, VM_RIGHTSIZE_FAMILY | — |

---

## Virtual machine scale set (`compute/vmss`)
ARM type: `Microsoft.Compute/virtualMachineScaleSets`
Synced properties: `virtualMachineProfile`, `sku`, `provisioningState`, `orchestrationMode`, `upgradePolicy`, `singlePlacementGroup`, `platformFaultDomainCount`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `vm_size` | VM size | `props:virtualMachineProfile.hardwareProfile.vmSize` | VM_IDLE, VM_OVERSIZE, VM_RIGHTSIZE_FAMILY |
| `instance_count` | Instance count | `sku:capacity` | VM_IDLE, AKS_UNDERUTILIZED |
| `time_created` | Oldest instance created | `props:oldest_instance_time_created` | VM_COMMITMENT_CANDIDATE |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `avg_cpu_pct` | Percentage CPU | both | VM_IDLE, VM_OVERSIZE, VM_RIGHTSIZE_FAMILY, VM_SKU_SIZING_EXTENDED | Low CPU enables idle VM removal and rightsizing savings (up to 90% MTD). |
| `avg_available_memory_bytes` | Available Memory Bytes | cost | VM_OVERSIZE, VM_SKU_SIZING_EXTENDED, VM_RIGHTSIZE_FAMILY | — |

---

## Container registry (`containers/acr`)
ARM type: `Microsoft.ContainerRegistry/registries`
Synced properties: `provisioningState`, `adminUserEnabled`, `policies`, `zoneRedundancy`, `publicNetworkAccess`, `networkRuleSet`, `privateEndpointConnections`, `replicationCount`, …

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `sku` | SKU | `row:sku` | ACR_PREMIUM_EXTENDED, ACR_STANDARD_EXTENDED, ACR_GEO_REPLICATION_EXTENDED, ACR_STORAGE_HIGH_EXTENDED, ACR_RETENTION_DISABLED_EXTENDED |
| `provisioning_state` | Provisioning state | `props:provisioningState` | ACR_PREMIUM_EXTENDED, ACR_STANDARD_EXTENDED |
| `admin_user_enabled` | Admin user enabled | `props:adminUserEnabled` | ACR_PREMIUM_EXTENDED |
| `zone_redundancy` | Zone redundancy | `props:zoneRedundancy` | ACR_PREMIUM_EXTENDED, ACR_GEO_REPLICATION_EXTENDED |
| `replication_count` | Geo-replication count | `computed:replication_count` | ACR_GEO_REPLICATION_EXTENDED, ACR_PREMIUM_EXTENDED |
| `retention_policy_enabled` | Retention policy enabled | `computed:retention_policy_enabled` | ACR_RETENTION_DISABLED_EXTENDED |
| `retention_policy_days` | Retention policy days | `computed:retention_policy_days` | ACR_RETENTION_DISABLED_EXTENDED |
| `private_endpoint_count` | Private endpoint count | `computed:private_endpoint_count` | ACR_PREMIUM_EXTENDED |
| `public_network_access` | Public network access | `props:publicNetworkAccess` | ACR_PREMIUM_EXTENDED |
| `network_default_action` | Network default action | `props:networkRuleSet.defaultAction` | ACR_PREMIUM_EXTENDED |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `pull_count` | TotalPullCount | cost | ACR_PREMIUM_EXTENDED, ACR_STANDARD_EXTENDED, ACR_STORAGE_HIGH_EXTENDED | Low pull volume supports Basic tier ACR instead of Premium. |
| `push_count` | TotalPushCount | cost | ACR_STORAGE_HIGH_EXTENDED | Low push volume with high storage supports image cleanup recommendations. |
| `storage_used_bytes` | StorageUsed | cost | ACR_PREMIUM_EXTENDED, ACR_STANDARD_EXTENDED, ACR_STORAGE_HIGH_EXTENDED, ACR_RETENTION_DISABLED_EXTENDED | High registry storage increases ongoing backup and tier costs. |

---

## AKS cluster (`containers/aks`)
ARM type: `Microsoft.ContainerService/managedClusters`
Synced properties: `kubernetesVersion`, `agentPoolProfiles`, `powerState`, `networkProfile`, `provisioningState`, `enableRBAC`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `kubernetes_version` | Kubernetes version | `props:kubernetesVersion` | AKS_OLD_VERSION |
| `pool_count` | Node pool count | `computed:pool_count` | AKS_EMPTY_POOL |
| `node_count` | Total node count | `computed:node_count` | AKS_EMPTY_POOL, AKS_UNDERUTILIZED |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `cluster_cpu_pct` | node_cpu_usage_percentage | both | AKS_UNDERUTILIZED, AKS_IDLE_POOL_EXTENDED | Idle AKS nodes can be scaled down for proportional compute savings. |
| `cluster_mem_pct` | node_memory_working_set_percentage | both | AKS_UNDERUTILIZED, AKS_IDLE_POOL_EXTENDED | Supports idle node pool reduction recommendations. |

---

## Cosmos DB account (`database/cosmosdb`)
ARM type: `Microsoft.DocumentDB/databaseAccounts`
Synced properties: `databaseAccountOfferType`, `capabilities`, `enableAutomaticFailover`, `provisioningState`, `enableFreeTier`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `serverless_enabled` | Serverless enabled | `computed:serverless_enabled` | COSMOS_SERVERLESS |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `request_count` | TotalRequests | cost | COSMOS_SERVERLESS, COSMOS_AUTOSCALE_EXTENDED | Low request volume supports plan downgrade or resource removal. |
| `total_ru` | TotalRequestUnits | cost | COSMOS_AUTOSCALE_EXTENDED | Low RU consumption supports autoscale or manual throughput reduction. |

---

## PostgreSQL flexible server (`database/postgresql`)
ARM type: `Microsoft.DBforPostgreSQL/flexibleServers`
Synced properties: `storage`, `highAvailability`, `state`, `version`, `backup`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `storage_gb` | Storage size (GB) | `props:storage.storageSizeGB` | POSTGRES_STORAGE_OVERSIZE |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `cpu_pct` | cpu_percent | both | POSTGRESQL_BURSTABLE_EXTENDED | Low SQL CPU supports serverless or lower tier migration. |
| `memory_pct` | memory_percent | both | POSTGRESQL_BURSTABLE_EXTENDED | Low Redis memory supports smaller cache SKU. |
| `storage_pct` | storage_percent | both | POSTGRES_STORAGE_EXTENDED | Low storage utilization supports storage tier reduction. |

---

## Azure Cache for Redis (`database/redis`)
ARM type: `Microsoft.Cache/redis`
Synced properties: `redisVersion`, `redisConfiguration`, `enableNonSslPort`, `provisioningState`, `shardCount`, `replicasPerMaster`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `maxmemory_policy` | Eviction policy | `props:redisConfiguration.maxmemoryPolicy` | REDIS_TIER_REVIEW |
| `shard_count` | Shard count | `props:shardCount` | REDIS_TIER_REVIEW |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `memory_pct` | usedmemorypercentage | both | REDIS_TIER_REVIEW, REDIS_RIGHTSIZE_EXTENDED | Low Redis memory supports smaller cache SKU. |
| `cache_hits` | cachehits | cost | REDIS_HEALTH_EXTENDED | — |

---

## SQL server (`database/sql`)
ARM type: `Microsoft.Sql/servers`
Synced properties: `version`, `state`, `minimalTlsVersion`, `publicNetworkAccess`

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `cpu_pct` | cpu_percent | both | SQL_IDLE, SQL_SERVERLESS_EXTENDED | Low SQL CPU supports serverless or lower tier migration. |
| `storage_pct` | storage_percent | both | SQL_IDLE | Low storage utilization supports storage tier reduction. |

---

## API Management (`integration/apim`)
ARM type: `Microsoft.ApiManagement/service`
Synced properties: `provisioningState`, `publisherEmail`, `virtualNetworkType`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `vnet_type` | VNet integration | `props:virtualNetworkType` | COST_APIM_REVIEW |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `request_count` | Requests | cost | COST_APIM_REVIEW | Low request volume supports plan downgrade or resource removal. |
| `capacity_pct` | Capacity | both | COST_APIM_REVIEW | — |

---

## Data Factory (`integration/datafactory`)
ARM type: `Microsoft.DataFactory/factories`
Synced properties: `provisioningState`, `publicNetworkAccess`

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `pipeline_succeeded` | PipelineSucceededRuns | both | — | — |
| `pipeline_failed` | PipelineFailedRuns | both | — | — |

---

## Logic App (`integration/logicapp`)
ARM type: `Microsoft.Logic/workflows`
Synced properties: `state`, `provisioningState`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `workflow_state` | Workflow state | `props:state` | COST_LOGIC_APP_REVIEW |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `runs_started` | RunsStarted | cost | COST_LOGIC_APP_REVIEW | — |
| `runs_completed` | RunsCompleted | cost | COST_LOGIC_APP_REVIEW | — |

---

## Event Hubs namespace (`messaging/eventhub`)
ARM type: `Microsoft.EventHub/namespaces`
Synced properties: `provisioningState`, `kafkaEnabled`, `isAutoInflateEnabled`

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `incoming_messages` | IncomingMessages | cost | — | — |
| `outgoing_messages` | OutgoingMessages | cost | — | — |

---

## Service Bus namespace (`messaging/servicebus`)
ARM type: `Microsoft.ServiceBus/namespaces`
Synced properties: `provisioningState`, `zoneRedundant`

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `active_messages` | ActiveMessages | cost | — | — |
| `incoming_requests` | IncomingRequests | cost | — | — |

---

## Application Insights (`monitoring/appinsights`)
ARM type: `Microsoft.Insights/components`
Synced properties: `Application_Type`, `provisioningState`, `WorkspaceResourceId`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `app_type` | Application type | `props:Application_Type` | COST_APP_INSIGHTS_REVIEW |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `request_count` | requests/count | cost | COST_APP_INSIGHTS_REVIEW | Low request volume supports plan downgrade or resource removal. |
| `availability_pct` | availabilityResults/availabilityPercentage | both | COST_APP_INSIGHTS_REVIEW | — |

---

## Log Analytics workspace (`monitoring/loganalytics`)
ARM type: `Microsoft.OperationalInsights/workspaces`
Synced properties: `provisioningState`, `retentionInDays`, `sku`, `features`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `retention_days` | Retention (days) | `props:retentionInDays` | COST_LOG_ANALYTICS_REVIEW |
| `sku` | SKU | `row:sku` | COST_LOG_ANALYTICS_REVIEW |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `ingestion_gb` | BillableIngestionGB | cost | COST_LOG_ANALYTICS_REVIEW | — |

---

## Application gateway (`network/appgateway`)
ARM type: `Microsoft.Network/applicationGateways`
Synced properties: `httpListeners`, `requestRoutingRules`, `backendAddressPools`, `backendHttpSettingsCollection`, `frontendIPConfigurations`, `frontendPorts`, `probes`, `sku`, …

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `http_listener_count` | HTTP listener count | `computed:http_listener_count` | APPGW_UNUSED, APP_GATEWAY_IDLE_EXTENDED |
| `sku_tier` | SKU tier | `row:sku` | APPGW_UNUSED |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `healthy_host_count` | HealthyHostCount | cost | APPGW_UNUSED, APP_GATEWAY_IDLE_EXTENDED | — |
| `throughput_bytes` | Throughput | cost | APP_GATEWAY_IDLE_EXTENDED | Idle Application Gateway may be deleted for fixed-cost savings (~40% MTD). |
| `request_count` | TotalRequests | cost | APP_GATEWAY_IDLE_EXTENDED | Low request volume supports plan downgrade or resource removal. |

---

## CDN profile (`network/cdn`)
ARM type: `Microsoft.Cdn/profiles`
Synced properties: `provisioningState`, `originResponseTimeout`, `resourceState`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `resource_state` | Resource state | `props:resourceState` | CDN_EGRESS_EXTENDED |
| `sku` | SKU | `row:sku` | CDN_EGRESS_EXTENDED |

---

## Azure Firewall (`network/firewall`)
ARM type: `Microsoft.Network/azureFirewalls`
Synced properties: `provisioningState`, `sku`, `firewallPolicy`, `threatIntelMode`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `sku_tier` | SKU tier | `row:sku` | FIREWALL_FIXED_COST_EXTENDED |
| `provisioning_state` | Provisioning state | `props:provisioningState` | FIREWALL_FIXED_COST_EXTENDED |

---

## Load balancer (`network/loadbalancer`)
ARM type: `Microsoft.Network/loadBalancers`
Synced properties: `backendAddressPools`, `frontendIPConfigurations`, `loadBalancingRules`, `probes`, `provisioningState`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `backend_pool_count` | Backend pool count | `computed:backend_pool_count` | LB_NO_BACKEND, LB_IDLE_EXTENDED |
| `all_backends_empty` | All backends empty | `computed:all_backends_empty` | LB_NO_BACKEND |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `backend_availability_pct` | DipAvailability | both | LB_NO_BACKEND, LB_IDLE_EXTENDED | Removing idle load balancer saves cost only when backends are empty. |
| `byte_count` | ByteCount | cost | LB_IDLE_EXTENDED | Low traffic on public IPs, NAT gateways, and load balancers may be removable. |

---

## NAT gateway (`network/nat`)
ARM type: `Microsoft.Network/natGateways`
Synced properties: `subnets`, `publicIpAddresses`, `provisioningState`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `subnet_count` | Subnet associations | `computed:subnet_count` | NAT_GATEWAY_IDLE |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `byte_count` | ByteCount | cost | NAT_GATEWAY_IDLE, NAT_GATEWAY_IDLE_EXTENDED | Low traffic on public IPs, NAT gateways, and load balancers may be removable. |
| `snat_connection_count` | SNATConnectionCount | cost | NAT_GATEWAY_IDLE_EXTENDED | — |

---

## Network interface (`network/nic`)
ARM type: `Microsoft.Network/networkInterfaces`
Synced properties: `virtualMachine`, `privateEndpoint`, `ipConfigurations`, `provisioningState`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `has_vm` | Attached to VM | `computed:has_vm` | NIC_UNATTACHED |
| `has_private_endpoint` | Private endpoint | `computed:has_private_endpoint` | NIC_UNATTACHED |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `bytes_received_rate` | BytesReceivedRate | both | NIC_UNATTACHED | — |
| `bytes_sent_rate` | BytesSentRate | both | NIC_UNATTACHED | — |

---

## Network security group (`network/nsg`)
ARM type: `Microsoft.Network/networkSecurityGroups`
Synced properties: `securityRules`, `subnets`, `networkInterfaces`, `provisioningState`

---

## Private DNS zone (`network/privatedns`)
ARM type: `Microsoft.Network/privateDnsZones`
Synced properties: `zoneType`, `numberOfRecordSets`, `maxNumberOfRecordSets`, `provisioningState`

---

## Private endpoint (`network/privateendpoint`)
ARM type: `Microsoft.Network/privateEndpoints`
Synced properties: `subnet`, `privateLinkServiceConnections`, `manualPrivateLinkServiceConnections`, `customDnsConfigs`, `privateDnsZoneGroups`, `provisioningState`

---

## Private link service (`network/privatelinkservice`)
ARM type: `Microsoft.Network/privateLinkServices`
Synced properties: `visibility`, `autoApproval`, `fqdns`, `ipConfigurations`, `privateEndpointConnections`, `provisioningState`

---

## Public IP address (`network/publicip`)
ARM type: `Microsoft.Network/publicIPAddresses`
Synced properties: `ipAddress`, `ipConfiguration`, `natGateway`, `publicIPAllocationMethod`, `provisioningState`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `allocation` | Association | `row:state` | IP_UNASSOCIATED, IP_IDLE_EXTENDED |
| `public_ip_allocation_method` | Allocation method | `props:publicIPAllocationMethod` | IP_UNASSOCIATED |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `byte_count` | ByteCount | cost | IP_IDLE_EXTENDED | Low traffic on public IPs, NAT gateways, and load balancers may be removable. |
| `packet_count` | PacketCount | cost | IP_IDLE_EXTENDED | — |

---

## Cognitive Search (`search/cognitivesearch`)
ARM type: `Microsoft.Search/searchServices`
Synced properties: `provisioningState`, `replicaCount`, `partitionCount`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `replica_count` | Replica count | `props:replicaCount` | COST_SEARCH_REVIEW |
| `partition_count` | Partition count | `props:partitionCount` | COST_SEARCH_REVIEW |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `throttled_search_pct` | ThrottledSearchQueriesPercentage | both | COST_SEARCH_REVIEW | Scaling up search replicas increases cost but may be required. |

---

## Key vault (`security/keyvault`)
ARM type: `Microsoft.KeyVault/vaults`
Synced properties: `enableSoftDelete`, `enableRbacAuthorization`, `enablePurgeProtection`, `sku`, `provisioningState`, `networkAcls`, `publicNetworkAccess`, `tenantId`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `sku` | SKU | `row:sku` | KEYVAULT_PREMIUM_EXTENDED, KEYVAULT_IDLE_EXTENDED, KEYVAULT_HIGH_OPS_EXTENDED |
| `soft_delete_enabled` | Soft delete | `props:enableSoftDelete` | KEYVAULT_SOFT_DELETE_OFF, KEYVAULT_PROTECTION_EXTENDED |
| `purge_protection_enabled` | Purge protection | `props:enablePurgeProtection` | KEYVAULT_SOFT_DELETE_OFF, KEYVAULT_PROTECTION_EXTENDED |
| `rbac_enabled` | RBAC authorization | `props:enableRbacAuthorization` | KEYVAULT_PROTECTION_EXTENDED |
| `public_network_access` | Public network access | `props:publicNetworkAccess` | KEYVAULT_PROTECTION_EXTENDED, KEYVAULT_PREMIUM_EXTENDED |
| `network_default_action` | Network default action | `computed:network_default_action` | KEYVAULT_PROTECTION_EXTENDED |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `api_hits` | ServiceApiHit | cost | KEYVAULT_IDLE_EXTENDED, KEYVAULT_PREMIUM_EXTENDED, KEYVAULT_HIGH_OPS_EXTENDED | Idle vaults may be deleted; high volume increases per-operation charges. |
| `api_results` | ServiceApiResult | both | KEYVAULT_HIGH_OPS_EXTENDED | — |
| `availability_pct` | Availability | both | KEYVAULT_IDLE_EXTENDED, KEYVAULT_HIGH_OPS_EXTENDED | — |

---

## Storage account (`storage/account`)
ARM type: `Microsoft.Storage/storageAccounts`
Synced properties: `kind`, `accessTier`, `minimumTlsVersion`, `supportsHttpsTrafficOnly`, `allowBlobPublicAccess`, `provisioningState`

### Properties (inventory)

| Fact | Label | Source | Rules |
|------|-------|--------|-------|
| `access_tier` | Access tier | `props:accessTier` | STORAGE_HOT_TIER, STORAGE_COOL_TIER |
| `kind` | Storage kind | `props:kind` | STORAGE_NO_LIFECYCLE |

### Metrics (Azure Monitor / agent)

| Fact | Azure metric | Impact | Rules | Cost effect |
|------|--------------|--------|-------|-------------|
| `used_capacity_bytes` | UsedCapacity | cost | STORAGE_NO_LIFECYCLE, STORAGE_LIFECYCLE_EXTENDED | Underused storage capacity supports tier and lifecycle policies. |
| `transaction_count` | Transactions | cost | STORAGE_NO_LIFECYCLE | Low transaction volume supports storage lifecycle / tier optimization. |

---
