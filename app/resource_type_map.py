"""Map blob CSV ResourceId / ResourceType values to canonical resource_snapshots types."""

from __future__ import annotations

from app.focus_mapping import normalize_arm_id

# ARM provider/type (lowercase) → canonical resource_snapshots.resource_type
ARM_PROVIDER_TO_INTERNAL: dict[str, str] = {
    # Compute
    "microsoft.compute/virtualmachines": "compute/vm",
    "microsoft.compute/virtualmachinescalesets": "compute/vmss",
    "microsoft.compute/disks": "compute/disk",
    "microsoft.compute/snapshots": "compute/snapshot",
    "microsoft.batch/batchaccounts": "compute/batch",
    "microsoft.desktopvirtualization/hostpools": "compute/avd",
    "microsoft.desktopvirtualization/workspaces": "compute/avd",
    # Containers
    "microsoft.containerservice/managedclusters": "containers/aks",
    "microsoft.containerregistry/registries": "containers/acr",
    "microsoft.containerinstance/containergroups": "containers/aci",
    # Storage
    "microsoft.storage/storageaccounts": "storage/account",
    # Network
    "microsoft.network/publicipaddresses": "network/publicip",
    "microsoft.network/virtualnetworks": "network/vnet",
    "microsoft.network/networkinterfaces": "network/nic",
    "microsoft.network/natgateways": "network/nat",
    "microsoft.network/loadbalancers": "network/loadbalancer",
    "microsoft.network/applicationgateways": "network/appgateway",
    "microsoft.network/networksecuritygroups": "network/nsg",
    "microsoft.network/privateendpoints": "network/privateendpoint",
    "microsoft.network/privatelinkservices": "network/privatelinkservice",
    "microsoft.network/privatednszones": "network/privatedns",
    "microsoft.network/dnszones": "network/dns",
    "microsoft.network/frontdoors": "network/frontdoor",
    "microsoft.network/azurefirewalls": "network/firewall",
    "microsoft.network/firewallpolicies": "network/firewall",
    "microsoft.network/expressroutecircuits": "network/expressroute",
    "microsoft.network/trafficmanagerprofiles": "network/trafficmanager",
    "microsoft.network/routetables": "network/routetable",
    "microsoft.network/vpngateways": "network/vpngateway",
    "microsoft.cdn/profiles": "network/cdn",
    # Databases
    "microsoft.sql/servers": "database/sql",
    "microsoft.sql/databases": "database/sql",
    "microsoft.documentdb/databaseaccounts": "database/cosmosdb",
    "microsoft.dbforpostgresql/flexibleservers": "database/postgresql",
    "microsoft.dbforpostgresql/servers": "database/postgresql",
    "microsoft.cache/redis": "database/redis",
    "microsoft.dbformysql/flexibleservers": "database/mysql",
    "microsoft.dbformysql/servers": "database/mysql",
    # App platform
    "microsoft.web/sites": "appservice/webapp",
    "microsoft.web/serverfarms": "appservice/plan",
    "microsoft.web/staticsites": "appservice/staticweb",
    # Security
    "microsoft.keyvault/vaults": "security/keyvault",
    # Monitoring
    "microsoft.operationalinsights/workspaces": "monitoring/loganalytics",
    "microsoft.insights/components": "monitoring/appinsights",
    "microsoft.insights/metricalerts": "monitoring/alerts",
    "microsoft.alertsmanagement/smartdetectoralertrules": "monitoring/alerts",
    # Integration
    "microsoft.logic/workflows": "integration/logicapp",
    "microsoft.datafactory/factories": "integration/datafactory",
    "microsoft.apimanagement/service": "integration/apim",
    # Messaging
    "microsoft.eventhub/namespaces": "messaging/eventhub",
    "microsoft.servicebus/namespaces": "messaging/servicebus",
    "microsoft.signalrservice/webpubsub": "messaging/signalr",
    # Analytics & ML
    "microsoft.databricks/workspaces": "analytics/databricks",
    "microsoft.synapse/workspaces": "analytics/synapse",
    "microsoft.kusto/clusters": "analytics/adx",
    "microsoft.hdinsight/clusters": "analytics/hdinsight",
    "microsoft.machinelearningservices/workspaces": "analytics/mlworkspace",
    "microsoft.powerbidedicated/capacities": "analytics/powerbi",
    # Backup & automation
    "microsoft.recoveryservices/vaults": "backup/recoveryvault",
    "microsoft.automation/automationaccounts": "automation/automation",
    # Search
    "microsoft.search/searchservices": "search/cognitivesearch",
}

# FOCUS ServiceName fallback when ResourceType is missing
SERVICE_NAME_TO_INTERNAL: dict[str, str] = {
    "virtual machines": "compute/vm",
    "virtual machine scale sets": "compute/vmss",
    "storage": "storage/account",
    "kubernetes service": "containers/aks",
    "container registry": "containers/acr",
    "container instances": "containers/aci",
    "sql database": "database/sql",
    "azure cosmos db": "database/cosmosdb",
    "azure database for postgresql": "database/postgresql",
    "azure database for mysql": "database/mysql",
    "azure cache for redis": "database/redis",
    "app service": "appservice/webapp",
    "azure app service": "appservice/webapp",
    "static web apps": "appservice/staticweb",
    "key vault": "security/keyvault",
    "virtual network": "network/vnet",
    "virtual networks": "network/vnet",
    "load balancer": "network/loadbalancer",
    "application gateway": "network/appgateway",
    "virtual network peering": "network/vnet",
    "bandwidth": "network/publicip",
    "ip addresses": "network/publicip",
    "azure firewall": "network/firewall",
    "azure front door": "network/frontdoor",
    "content delivery network": "network/cdn",
    "azure private link": "network/privateendpoint",
    "private link": "network/privateendpoint",
    "nat gateway": "network/nat",
    "azure nat gateway": "network/nat",
    "vpn gateway": "network/vpngateway",
    "virtual wan": "network/vnet",
    "network watcher": "network/vnet",
    "log analytics": "monitoring/loganalytics",
    "microsoft.insights": "monitoring/appinsights",
    "application insights": "monitoring/appinsights",
    "azure monitor": "monitoring/alerts",
    "logic apps": "integration/logicapp",
    "azure data factory": "integration/datafactory",
    "data factory": "integration/datafactory",
    "api management": "integration/apim",
    "event hubs": "messaging/eventhub",
    "service bus": "messaging/servicebus",
    "azure databricks": "analytics/databricks",
    "azure synapse analytics": "analytics/synapse",
    "azure data explorer": "analytics/adx",
    "azure hdinsight": "analytics/hdinsight",
    "azure machine learning": "analytics/mlworkspace",
    "power bi embedded": "analytics/powerbi",
    "backup": "backup/recoveryvault",
    "recovery services": "backup/recoveryvault",
    "automation": "automation/automation",
    "azure cognitive search": "search/cognitivesearch",
    "search": "search/cognitivesearch",
}


def arm_provider_type(resource_id: str) -> str:
    """Return microsoft.provider/resourcetype from an ARM ID."""
    rid = normalize_arm_id(resource_id)
    if not rid:
        return ""
    parts = rid.split("/")
    try:
        idx = parts.index("providers")
        if idx + 2 < len(parts):
            return f"{parts[idx + 1]}/{parts[idx + 2]}".lower()
    except ValueError:
        pass
    return ""


def extract_rg_from_arm(resource_id: str) -> str:
    try:
        parts = resource_id.split("/")
        idx = [p.lower() for p in parts].index("resourcegroups")
        return parts[idx + 1]
    except Exception:
        return ""


def resource_name_from_arm_id(resource_id: str) -> str:
    rid = normalize_arm_id(resource_id)
    if not rid:
        return ""
    return rid.rsplit("/", 1)[-1]


def internal_resource_type(
    resource_id: str,
    blob_resource_type: str = "",
    service_name: str = "",
) -> str:
    """Resolve canonical type for a cost-export resource row."""
    for candidate in (
        (blob_resource_type or "").strip().lower(),
        arm_provider_type(resource_id),
    ):
        if not candidate:
            continue
        if candidate in ARM_PROVIDER_TO_INTERNAL:
            return ARM_PROVIDER_TO_INTERNAL[candidate]
        for arm_key, internal in ARM_PROVIDER_TO_INTERNAL.items():
            if candidate.endswith(arm_key.split("/", 1)[-1]):
                return internal

    svc = (service_name or "").strip().lower()
    if svc in SERVICE_NAME_TO_INTERNAL:
        return SERVICE_NAME_TO_INTERNAL[svc]
    for key, internal in SERVICE_NAME_TO_INTERNAL.items():
        if key in svc:
            return internal

    provider = arm_provider_type(resource_id)
    if provider:
        slug = provider.replace("/", "-")
        return f"other/{slug}"
    return "other/unknown"


def is_known_internal_type(resource_type: str) -> bool:
    return not (resource_type or "").startswith("other/")


def all_known_arm_resource_types() -> list[str]:
    """Distinct ARM provider/types used for Cost Management ResourceType filters."""
    return sorted(ARM_PROVIDER_TO_INTERNAL.keys())


def arm_types_for_canonical(canonical_type: str) -> list[str]:
    """ARM ResourceType values that map to a canonical inventory type."""
    return sorted(
        arm for arm, internal in ARM_PROVIDER_TO_INTERNAL.items() if internal == canonical_type
    )


def inventory_canonical_for_arm_type(arm_type: str) -> str | None:
    """Exact ARM list type → canonical inventory type, or None if not in our layout.

    Uses exact provider/type matching only (no suffix fallbacks) so child resources
    like ``virtualmachines/extensions`` are not misclassified.
    """
    from app.resources.registry import get_technical_fetch_spec_by_arm
    from app.sync_scope import inventory_syncable_types

    arm = (arm_type or "").strip().lower()
    if not arm:
        return None
    syncable = inventory_syncable_types()
    spec = get_technical_fetch_spec_by_arm(arm)
    if spec and spec.canonical_type in syncable:
        return spec.canonical_type
    canonical = ARM_PROVIDER_TO_INTERNAL.get(arm)
    if canonical and canonical in syncable:
        return canonical
    return None


# Dashboard / counts: aggregate canonical types under short keys
TYPE_PREFIX_TO_COUNT_KEY: dict[str, str] = {
    "network/cdn": "cdn",
    "network/frontdoor": "frontdoor",
    "network/firewall": "firewall",
    "compute/vmss": "vmss",
    "compute/batch": "batch",
    "compute/avd": "avd",
    "containers/aci": "aci",
    "appservice/staticweb": "staticweb",
    "database/mysql": "mysql",
    "automation/": "automation",
}


def count_key_for_type(canonical_type: str) -> str | None:
    """Map a canonical resource type to a dashboard count key, if any."""
    from app.resource_page_registry import count_key_for_canonical

    key = count_key_for_canonical(canonical_type)
    if key:
        return key
    if not canonical_type:
        return None
    for prefix, count_key in TYPE_PREFIX_TO_COUNT_KEY.items():
        if canonical_type.startswith(prefix) or canonical_type == prefix.rstrip("/"):
            return count_key
    return None
