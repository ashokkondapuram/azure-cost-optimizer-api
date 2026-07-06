"""ARM REST API versions — aligned with Microsoft Learn provider docs.

References:
- Compute: https://learn.microsoft.com/en-us/rest/api/compute/
- Network: https://learn.microsoft.com/en-us/rest/api/virtualnetwork/
- AKS: https://learn.microsoft.com/en-us/rest/api/aks/
- Monitor metrics: https://learn.microsoft.com/en-us/rest/api/monitor/metrics/list
"""

from __future__ import annotations

# Azure Monitor Metrics List
MONITOR_METRICS_API_VERSION = "2023-10-01"

# Generic Resources / Resource Groups list
RESOURCES_LIST_API_VERSION = "2024-03-01"
SUBSCRIPTIONS_LIST_API_VERSION = "2022-12-01"

# Typed list + GET api-version per ARM provider/type (lowercase keys).
ARM_GET_API_VERSIONS: dict[str, str] = {
    # Compute — https://learn.microsoft.com/en-us/rest/api/compute/
    "microsoft.compute/virtualmachines": "2025-11-01",
    "microsoft.compute/virtualmachinescalesets": "2025-11-01",
    "microsoft.compute/disks": "2026-03-02",
    "microsoft.compute/snapshots": "2026-03-02",
    # Containers
    "microsoft.containerservice/managedclusters": "2025-10-01",
    "microsoft.containerregistry/registries": "2025-04-01",
    # Storage — https://learn.microsoft.com/en-us/rest/api/storagerp/
    "microsoft.storage/storageaccounts": "2026-04-01",
    # Network — https://learn.microsoft.com/en-us/rest/api/virtualnetwork/
    "microsoft.network/virtualnetworks": "2024-05-01",
    "microsoft.network/publicipaddresses": "2024-05-01",
    "microsoft.network/loadbalancers": "2024-05-01",
    "microsoft.network/applicationgateways": "2025-05-01",
    "microsoft.network/networkinterfaces": "2024-05-01",
    "microsoft.network/natgateways": "2024-05-01",
    "microsoft.network/networksecuritygroups": "2024-05-01",
    "microsoft.network/privateendpoints": "2024-05-01",
    "microsoft.network/privatelinkservices": "2024-05-01",
    "microsoft.network/privatednszones": "2024-06-01",
    # Databases
    # FIX: was "2023-08-01-preview" (preview-only, never GA'd) — use stable 2021-11-01
    "microsoft.sql/servers": "2021-11-01",
    "microsoft.sql/servers/databases": "2021-11-01",
    "microsoft.documentdb/databaseaccounts": "2024-05-15",
    "microsoft.dbforpostgresql/flexibleservers": "2024-08-01",
    "microsoft.cache/redis": "2024-11-01",
    # App Service — https://learn.microsoft.com/en-us/rest/api/appservice/
    "microsoft.web/sites": "2024-04-01",
    "microsoft.web/serverfarms": "2024-04-01",
    # Security
    "microsoft.keyvault/vaults": "2024-11-01",
    # Monitoring
    "microsoft.operationalinsights/workspaces": "2025-02-01",
    "microsoft.insights/components": "2020-02-02",
    # Integration
    # FIX: was "2024-06-01-preview" — use stable 2024-05-01
    "microsoft.apimanagement/service": "2024-05-01",
    "microsoft.datafactory/factories": "2018-06-01",
    "microsoft.logic/workflows": "2019-05-01",
    # Messaging
    # FIX: was "2024-05-01-preview" — use stable 2024-01-01
    "microsoft.eventhub/namespaces": "2024-01-01",
    # FIX: was "2022-10-01-preview" — use stable 2022-10-01
    "microsoft.servicebus/namespaces": "2022-10-01",
    # Analytics
    "microsoft.databricks/workspaces": "2024-05-01",
    "microsoft.synapse/workspaces": "2021-06-01",
    "microsoft.kusto/clusters": "2024-04-13",
    "microsoft.machinelearningservices/workspaces": "2024-10-01",
    # Backup & Search
    "microsoft.recoveryservices/vaults": "2024-04-01",
    # FIX: was "2024-06-01-preview" — use stable 2023-11-01
    "microsoft.search/searchservices": "2023-11-01",
}

ARM_GET_DEFAULT_API_VERSION = "2024-05-01"


def api_version_for_arm_type(arm_type: str) -> str:
    """Resolve GET api-version for a lowercase ARM provider/type string."""
    return ARM_GET_API_VERSIONS.get((arm_type or "").strip().lower(), ARM_GET_DEFAULT_API_VERSION)
