"""Parallel ARM list fetching for db_sync (1-F extension)."""

from __future__ import annotations

from typing import Any, Callable

from app.parallel_arm_sync import parallel_fetch

# Canonical type → AzureResourcesClient list method (excluding compute trio).
ARM_LIST_METHODS: dict[str, str] = {
    "containers/aks": "list_aks_clusters",
    "storage/account": "list_storage_accounts",
    "network/publicip": "list_public_ips",
    "database/sql": "list_sql_servers",
    "security/keyvault": "list_keyvaults",
    "appservice/webapp": "list_app_services",
    "appservice/plan": "list_app_service_plans",
    "network/loadbalancer": "list_load_balancers",
    "network/appgateway": "list_application_gateways",
    "network/nsg": "list_network_security_groups",
    "network/nic": "list_network_interfaces",
    "network/nat": "list_nat_gateways",
    "network/vnet": "list_vnets",
    "network/privateendpoint": "list_private_endpoints",
    "network/privatelinkservice": "list_private_link_services",
    "network/privatedns": "list_private_dns_zones",
    "database/cosmosdb": "list_cosmosdb",
    "database/postgresql": "list_postgresql_flexible",
    "database/redis": "list_redis_caches",
    "containers/acr": "list_container_registries",
}

_COMPUTE_TRIO = frozenset({"compute/vm", "compute/disk", "compute/snapshot"})


def fetch_arm_lists_parallel(
    client: Any,
    subscription_id: str,
    want: Callable[[str], bool],
    *,
    exclude: frozenset[str] | None = None,
) -> dict[str, list]:
    """Fetch independent ARM resource lists in parallel."""
    skip = exclude or _COMPUTE_TRIO
    specs: list[tuple[str, Callable[[], list]]] = []
    for canonical, method_name in ARM_LIST_METHODS.items():
        if canonical in skip or not want(canonical):
            continue
        method = getattr(client, method_name)
        specs.append((canonical, lambda m=method: m(subscription_id)))
    if not specs:
        return {}
    if len(specs) == 1:
        key, fn = specs[0]
        return {key: fn()}
    return parallel_fetch(specs)
