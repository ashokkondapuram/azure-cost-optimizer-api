# IT services — file organization

Each Azure resource type has a dedicated folder for **backend** and **frontend** code. This is organizational structure only — the app still runs as one deployment.

## Quick start

1. Find your resource in the [catalog](#all-services) below.
2. Open `it-services/<service-id>/manifest.yaml` for owned paths.
3. Edit `it_services/<service_pkg>/` (backend) and `frontend/src/it-services/<service-id>/` (frontend).
4. Enable custom drawer UI in `frontend/src/it-services/registry.js` when ready (`drawer_ui: true` in manifest).

Machine-readable index: [catalog.json](catalog.json)

## Layout

```
it-services/<service-id>/          # Manifest + docs
it_services/<service_pkg>/         # Backend Python
frontend/src/it-services/<id>/   # Frontend React
```

Platform shell (`app/`, `frontend/src/config/`, shared drawer) stays shared.

## Engine organization

Only **platform-independent** optimizer code lives outside IT service folders:

```
app/optimizer/platform/
  runtime/                 # ResourceSubEngine base, context, envelope
  cost/                    # Budget, commitments, anomaly (subscription-level)
  sub_engine_registry.py   # Loads per-resource sub-engines
  analysis_batches.py      # Batch ordering for parallel analysis

it_services/<service_pkg>/engine/
  sub_engine.py            # Resource-specific sub-engine
  analysis.py              # Analysis rules for this resource
  optimization_rules.py    # Optional decision rules

app/optimizer/resource_engines/   # Legacy compatibility shims only
```

Regenerate engine layout after changes:

```bash
python3 scripts/organize-engines-to-it-services.py
python3 scripts/migrate-it-service-assets.py
```

## All services (42)

| Display name | Service ID | Canonical type | API path | Drawer UI |
|--------------|------------|----------------|----------|-----------|
| [Azure Data Explorer](analytics-adx/README.md) | `analytics-adx` | `analytics/adx` | `/resources/adx` | — |
| [Azure Databricks](analytics-databricks/README.md) | `analytics-databricks` | `analytics/databricks` | `/resources/databricks` | — |
| [Azure ML workspace](analytics-mlworkspace/README.md) | `analytics-mlworkspace` | `analytics/mlworkspace` | `/resources/mlworkspace` | — |
| [Azure Synapse](analytics-synapse/README.md) | `analytics-synapse` | `analytics/synapse` | `/resources/synapse` | — |
| [App Service plan](appservice-plan/README.md) | `appservice-plan` | `appservice/plan` | `/resources/appserviceplans` | — |
| [App Service](appservice-webapp/README.md) | `appservice-webapp` | `appservice/webapp` | `/resources/appservices` | — |
| [Recovery Services vault](backup-recoveryvault/README.md) | `backup-recoveryvault` | `backup/recoveryvault` | `/resources/recoveryvault` | — |
| [Managed disk](compute-disk/README.md) | `compute-disk` | `compute/disk` | `/resources/disks` | yes |
| [Disk snapshot](compute-snapshot/README.md) | `compute-snapshot` | `compute/snapshot` | `/resources/snapshots` | — |
| [Virtual machine](compute-vm/README.md) | `compute-vm` | `compute/vm` | `/resources/vms` | — |
| [Virtual machine scale set](compute-vmss/README.md) | `compute-vmss` | `compute/vmss` | `/resources/vmss` | — |
| [Container registry](containers-acr/README.md) | `containers-acr` | `containers/acr` | `/resources/acr` | — |
| [AKS cluster](containers-aks/README.md) | `containers-aks` | `containers/aks` | `/resources/aks` | — |
| [Cosmos DB account](database-cosmosdb/README.md) | `database-cosmosdb` | `database/cosmosdb` | `/resources/cosmosdb` | — |
| [PostgreSQL flexible server](database-postgresql/README.md) | `database-postgresql` | `database/postgresql` | `/resources/postgresql` | — |
| [Azure Cache for Redis](database-redis/README.md) | `database-redis` | `database/redis` | `/resources/redis` | — |
| [SQL server](database-sql/README.md) | `database-sql` | `database/sql` | `/resources/sql` | — |
| [API Management](integration-apim/README.md) | `integration-apim` | `integration/apim` | `/resources/apim` | — |
| [Data Factory](integration-datafactory/README.md) | `integration-datafactory` | `integration/datafactory` | `/resources/datafactory` | — |
| [Logic App](integration-logicapp/README.md) | `integration-logicapp` | `integration/logicapp` | `/resources/logicapps` | — |
| [Event Hubs namespace](messaging-eventhub/README.md) | `messaging-eventhub` | `messaging/eventhub` | `/resources/eventhubs` | — |
| [Service Bus namespace](messaging-servicebus/README.md) | `messaging-servicebus` | `messaging/servicebus` | `/resources/servicebus` | — |
| [Application Insights](monitoring-appinsights/README.md) | `monitoring-appinsights` | `monitoring/appinsights` | `/resources/appinsights` | — |
| [Log Analytics workspace](monitoring-loganalytics/README.md) | `monitoring-loganalytics` | `monitoring/loganalytics` | `/resources/loganalytics` | — |
| [Application gateway](network-appgateway/README.md) | `network-appgateway` | `network/appgateway` | `/resources/appgateways` | — |
| [CDN profile](network-cdn/README.md) | `network-cdn` | `network/cdn` | `/resources/cdn` | — |
| [ExpressRoute circuit](network-expressroute/README.md) | `network-expressroute` | `network/expressroute` | `/resources/expressroute` | — |
| [Azure Firewall](network-firewall/README.md) | `network-firewall` | `network/firewall` | `/resources/firewall` | — |
| [Azure Front Door](network-frontdoor/README.md) | `network-frontdoor` | `network/frontdoor` | `/resources/frontdoor` | — |
| [Load balancer](network-loadbalancer/README.md) | `network-loadbalancer` | `network/loadbalancer` | `/resources/loadbalancers` | — |
| [NAT gateway](network-nat/README.md) | `network-nat` | `network/nat` | `/resources/natgateways` | — |
| [Network interface](network-nic/README.md) | `network-nic` | `network/nic` | `/resources/nics` | — |
| [Network security group](network-nsg/README.md) | `network-nsg` | `network/nsg` | `/resources/nsgs` | — |
| [Private DNS zone](network-privatedns/README.md) | `network-privatedns` | `network/privatedns` | `/resources/privatedns` | — |
| [Private endpoint](network-privateendpoint/README.md) | `network-privateendpoint` | `network/privateendpoint` | `/resources/privateendpoints` | — |
| [Private link service](network-privatelinkservice/README.md) | `network-privatelinkservice` | `network/privatelinkservice` | `/resources/privatelinkservices` | — |
| [Public IP address](network-publicip/README.md) | `network-publicip` | `network/publicip` | `/resources/publicips` | — |
| [Traffic Manager profile](network-trafficmanager/README.md) | `network-trafficmanager` | `network/trafficmanager` | `/resources/trafficmanager` | — |
| [Virtual network](network-vnet/README.md) | `network-vnet` | `network/vnet` | `/resources/vnets` | — |
| [Cognitive Search](search-cognitivesearch/README.md) | `search-cognitivesearch` | `search/cognitivesearch` | `/resources/cognitivesearch` | — |
| [Key vault](security-keyvault/README.md) | `security-keyvault` | `security/keyvault` | `/resources/keyvaults` | — |
| [Storage account](storage-account/README.md) | `storage-account` | `storage/account` | `/resources/storage` | — |

## Scaffold

```bash
python3 scripts/scaffold-it-services.py --all
python3 scripts/scaffold-it-services.py --service compute-vm
```
