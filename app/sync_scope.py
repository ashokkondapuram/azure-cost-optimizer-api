"""Map API paths and short keys to canonical resource types for scoped Azure sync."""

from __future__ import annotations

from app.optimizer.component_map import COMPONENT_RESOURCE_TYPES
from app.resource_page_registry import (
    API_PATH_TO_CANONICAL,
    COUNT_KEY_TO_CANONICAL,
)
from app.resource_store import RESOURCE_COUNTS_KEYS

# GET list endpoint → single canonical type stored in resource_snapshots
API_PATH_TO_TYPE: dict[str, str] = {
    "/resources/vms": "compute/vm",
    "/resources/vmss": "compute/vmss",
    "/resources/disks": "compute/disk",
    "/resources/snapshots": "compute/snapshot",
    "/resources/aks": "containers/aks",
    "/resources/acr": "containers/acr",
    "/resources/storage": "storage/account",
    "/resources/publicips": "network/publicip",
    "/resources/vnets": "network/vnet",
    "/resources/nics": "network/nic",
    "/resources/natgateways": "network/nat",
    "/resources/loadbalancers": "network/loadbalancer",
    "/resources/appgateways": "network/appgateway",
    "/resources/nsgs": "network/nsg",
    "/resources/privateendpoints": "network/privateendpoint",
    "/resources/privatelinkservices": "network/privatelinkservice",
    "/resources/privatedns": "network/privatedns",
    "/resources/sql": "database/sql",
    "/resources/cosmosdb": "database/cosmosdb",
    "/resources/postgresql": "database/postgresql",
    "/resources/redis": "database/redis",
    "/resources/appservices": "appservice/webapp",
    "/resources/appserviceplans": "appservice/plan",
    "/resources/keyvaults": "security/keyvault",
    **API_PATH_TO_CANONICAL,
}

# Legacy aggregate list pages → optimization component label
API_PATH_TO_COMPONENT: dict[str, str] = {
    "/resources/monitoring": "Monitoring",
    "/resources/integration": "Integration",
    "/resources/messaging": "Messaging",
    "/resources/analytics": "Analytics",
    "/resources/backup": "Backup",
    "/resources/search": "Search",
}

COUNT_KEY_TO_TYPE: dict[str, str] = {
    **RESOURCE_COUNTS_KEYS,
    **COUNT_KEY_TO_CANONICAL,
}

# Per-type count keys from the inventory page registry
PER_TYPE_COUNT_KEYS: frozenset[str] = frozenset(COUNT_KEY_TO_CANONICAL.keys())

_ALL_CANONICAL_TYPES: set[str] = set()
for _types in COMPONENT_RESOURCE_TYPES.values():
    _ALL_CANONICAL_TYPES.update(_types)


def inventory_syncable_types() -> frozenset[str]:
    """Canonical types persisted to resource_snapshots by inventory sync."""
    return frozenset(_ALL_CANONICAL_TYPES)


def _types_for_prefix(prefix: str) -> list[str]:
    return sorted(t for t in _ALL_CANONICAL_TYPES if t.startswith(prefix))


def canonical_type_from_api_path(api_path: str) -> str | None:
    path = (api_path or "").strip().lower().rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    return API_PATH_TO_TYPE.get(path)


def canonical_type_from_count_key(count_key: str) -> str | None:
    return COUNT_KEY_TO_TYPE.get((count_key or "").strip().lower())


def types_for_api_path(api_path: str) -> list[str]:
    """Canonical types to sync when fetching from a resource list page."""
    path = (api_path or "").strip().lower().rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    component = API_PATH_TO_COMPONENT.get(path)
    if component:
        return list(COMPONENT_RESOURCE_TYPES.get(component, []))
    canonical = API_PATH_TO_TYPE.get(path)
    return [canonical] if canonical else []


def normalize_sync_types(types: list[str] | None) -> set[str] | None:
    """
    Normalize caller-provided type identifiers to canonical types.
    Accepts canonical types, count keys (vms, disks), API paths (/resources/vms),
    or category prefixes (monitoring/).
    Returns None when types is None (full inventory sync).
    """
    if types is None:
        return None
    out: set[str] = set()
    for raw in types:
        token = (raw or "").strip().lower()
        if not token:
            continue
        if token.startswith("/resources/"):
            out.update(types_for_api_path(token))
            continue
        if token in COUNT_KEY_TO_TYPE:
            mapped = COUNT_KEY_TO_TYPE[token]
            if mapped == "cost/all":
                continue
            out.add(mapped)
            continue
        if token in PER_TYPE_COUNT_KEYS:
            mapped = COUNT_KEY_TO_CANONICAL.get(token)
            if mapped:
                out.add(mapped)
            continue
        if token.endswith("/"):
            out.update(_types_for_prefix(token))
            continue
        if "/" in token:
            out.add(token)
    return out


def inventory_page_catalog() -> list[dict]:
    from app.resource_page_registry import pages_catalog

    return pages_catalog()
