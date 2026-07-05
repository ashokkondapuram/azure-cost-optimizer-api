"""Map UI components ↔ DB resource types ↔ engine buckets."""

from __future__ import annotations

# Component label → canonical resource_snapshot.resource_type values
COMPONENT_RESOURCE_TYPES: dict[str, list[str]] = {
    "Virtual Machines": ["compute/vm"],
    "Virtual Machine Scale Sets": ["compute/vmss"],
    "Managed Disks": ["compute/disk"],
    "Disk Snapshots": ["compute/snapshot"],
    "App Service": ["appservice/webapp", "appservice/plan"],
    "AKS": ["containers/aks"],
    "Storage Accounts": ["storage/account"],
    "Public IPs": ["network/publicip"],
    "Network Interfaces": ["network/nic"],
    "NAT Gateways": ["network/nat"],
    "Network Security Groups": ["network/nsg"],
    "Load Balancers": ["network/loadbalancer"],
    "Application Gateways": ["network/appgateway"],
    "SQL Database": ["database/sql"],
    "PostgreSQL": ["database/postgresql"],
    "Cosmos DB": ["database/cosmosdb"],
    "Redis Cache": ["database/redis"],
    "Container Registry": ["containers/acr"],
    "Key Vault": ["security/keyvault"],
    "Monitoring": ["monitoring/loganalytics", "monitoring/appinsights"],
    "Integration": ["integration/apim", "integration/datafactory", "integration/logicapp"],
    "Messaging": ["messaging/eventhub", "messaging/servicebus"],
    "Analytics": ["analytics/databricks", "analytics/synapse", "analytics/adx", "analytics/mlworkspace"],
    "Backup": ["backup/recoveryvault"],
    "Search": ["search/cognitivesearch"],
    "Networking": ["network/firewall", "network/cdn"],
    "Networking Extended": ["network/vnet", "network/privateendpoint", "network/privatelinkservice", "network/privatedns"],
}

# Batched analysis order — one component per batch to limit memory/CPU spikes
ANALYSIS_BATCHES: list[dict] = [
    {"component": "Virtual Machines", "buckets": ["vms"]},
    {"component": "Virtual Machine Scale Sets", "buckets": ["vmss"]},
    {"component": "Managed Disks", "buckets": ["disks"]},
    {"component": "Disk Snapshots", "buckets": ["snapshots"]},
    {"component": "AKS", "buckets": ["aks_clusters"]},
    {"component": "App Service", "buckets": ["app_services", "app_service_plans"]},
    {"component": "Storage Accounts", "buckets": ["storage"]},
    {"component": "Public IPs", "buckets": ["public_ips"]},
    {"component": "Network Interfaces", "buckets": ["network_interfaces"]},
    {"component": "NAT Gateways", "buckets": ["nat_gateways"]},
    {"component": "Network Security Groups", "buckets": ["nsgs"]},
    {"component": "Load Balancers", "buckets": ["load_balancers"]},
    {"component": "Application Gateways", "buckets": ["app_gateways"]},
    {"component": "SQL Database", "buckets": ["sql_servers", "sql_databases"]},
    {"component": "PostgreSQL", "buckets": ["postgresql"]},
    {"component": "Cosmos DB", "buckets": ["cosmosdb"]},
    {"component": "Redis Cache", "buckets": ["redis_caches"]},
    {"component": "Container Registry", "buckets": ["container_registries"]},
    {"component": "Key Vault", "buckets": ["keyvaults"]},
    {"component": "Monitoring", "buckets": ["log_analytics_workspaces", "app_insights_components"]},
    {"component": "Integration", "buckets": ["apim_services", "data_factories", "logic_apps"]},
    {"component": "Messaging", "buckets": ["event_hubs", "service_bus_namespaces"]},
    {"component": "Analytics", "buckets": ["databricks_workspaces", "synapse_workspaces", "adx_clusters", "ml_workspaces"]},
    {"component": "Backup", "buckets": ["recovery_vaults"]},
    {"component": "Search", "buckets": ["cognitive_search_services"]},
    {"component": "Networking", "buckets": ["firewalls", "cdn_profiles"]},
    {"component": "Networking Extended", "buckets": ["vnets", "private_endpoints", "private_link_services", "private_dns_zones"]},
    {"component": "Cost Anomalies", "buckets": ["cost_anomalies"]},
    {"component": "Commitments", "buckets": ["vms"]},
    {"component": "Budgets", "buckets": ["budgets"]},
]

IDLE_STATE_PATTERNS = (
    "stopped", "deallocated", "unattached", "unassociated", "failed", "disabled", "idle",
)

# Subset used for optimization-center waste KPIs (excludes deallocated VMs).
WASTE_STATE_PATTERNS = (
    "stopped", "unattached", "unassociated", "failed", "disabled", "idle",
)

CANONICAL_TO_COMPONENT: dict[str, str] = {}
for _comp, _types in COMPONENT_RESOURCE_TYPES.items():
    for _t in _types:
        CANONICAL_TO_COMPONENT[_t] = _comp


def resolve_batches(components: list[str] | None = None) -> list[dict]:
    """Return analysis batches for all components or a scoped subset."""
    if not components:
        return list(ANALYSIS_BATCHES)
    want = set(components)
    batches = [b for b in ANALYSIS_BATCHES if b["component"] in want]
    if not batches:
        raise ValueError(f"No analysis batches match components: {sorted(want)}")
    return batches


def resource_types_for_components(components: list[str]) -> set[str]:
    """Canonical resource types covered by the given components."""
    types: set[str] = set()
    for comp in components:
        types.update(COMPONENT_RESOURCE_TYPES.get(comp, []))
    return types


def sync_types_for_component(component: str) -> list[str]:
    """Canonical types to sync when refreshing one optimization component."""
    return list(COMPONENT_RESOURCE_TYPES.get(component, []))
