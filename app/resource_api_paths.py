"""Canonical resource API paths — single source for inventory list routes.

Primary list path: ``/resources/{canonical_type}`` (e.g. ``/resources/compute/disk``).
Legacy slug paths (``/resources/disks``) remain registered as aliases for compatibility.
"""

from __future__ import annotations

from app.inventory_standalone import is_standalone_inventory_type
from app.resource_page_registry import inventory_pages
LEGACY_SLUG_TO_CANONICAL: dict[str, str] = {
    "vms": "compute/vm",
    "disks": "compute/disk",
    "snapshots": "compute/snapshot",
    "aks": "containers/aks",
    "acr": "containers/acr",
    "storage": "storage/account",
    "publicips": "network/publicip",
    "vnets": "network/vnet",
    "nics": "network/nic",
    "natgateways": "network/nat",
    "loadbalancers": "network/loadbalancer",
    "appgateways": "network/appgateway",
    "nsgs": "network/nsg",
    "privateendpoints": "network/privateendpoint",
    "privatelinkservices": "network/privatelinkservice",
    "privatedns": "network/privatedns",
    "sql": "database/sql",
    "cosmosdb": "database/cosmosdb",
    "postgresql": "database/postgresql",
    "redis": "database/redis",
    "appservices": "appservice/webapp",
    "appserviceplans": "appservice/plan",
    "keyvaults": "security/keyvault",
}

def _merge_per_type_slugs() -> None:
    for _page in inventory_pages():
        if is_standalone_inventory_type(_page.canonical_type):
            LEGACY_SLUG_TO_CANONICAL.setdefault(_page.api_slug, _page.canonical_type)


_merge_per_type_slugs()

LEGACY_AGGREGATE_SLUGS: dict[str, tuple[str, ...]] = {
    "monitoring": ("monitoring/loganalytics", "monitoring/appinsights"),
    "integration": ("integration/apim", "integration/datafactory", "integration/logicapp"),
    "messaging": ("messaging/eventhub", "messaging/servicebus"),
    "analytics": (
        "analytics/databricks",
        "analytics/synapse",
        "analytics/adx",
        "analytics/mlworkspace",
    ),
    "backup": ("backup/recoveryvault",),
    "search": ("search/cognitivesearch",),
}


def canonical_api_path(canonical_type: str) -> str:
    ct = (canonical_type or "").strip().lower()
    return f"/resources/{ct}"


def legacy_slug_api_path(slug: str) -> str:
    return f"/resources/{(slug or '').strip().lower()}"


def _build_maps() -> tuple[dict[str, str], dict[str, str]]:
    canonical_to_path: dict[str, str] = {}
    path_to_canonical: dict[str, str] = {}

    for slug, ct in LEGACY_SLUG_TO_CANONICAL.items():
        legacy = legacy_slug_api_path(slug)
        canonical = canonical_api_path(ct)
        canonical_to_path[ct] = canonical
        path_to_canonical[legacy] = ct
        path_to_canonical[canonical] = ct

    for slug, types in LEGACY_AGGREGATE_SLUGS.items():
        path_to_canonical[legacy_slug_api_path(slug)] = types[0]  # primary for icon/sync hints

    return canonical_to_path, path_to_canonical


CANONICAL_TO_API_PATH, API_PATH_TO_CANONICAL = _build_maps()


def canonical_from_api_path(api_path: str) -> str | None:
    path = (api_path or "").strip().lower().rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    ct = API_PATH_TO_CANONICAL.get(path)
    if ct and not is_standalone_inventory_type(ct):
        return None
    return ct


def canonical_types_for_api_path(api_path: str) -> list[str]:
    path = (api_path or "").strip().lower().rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    slug = path.removeprefix("/resources/").strip("/")
    if slug in LEGACY_AGGREGATE_SLUGS:
        return [
            ct for ct in LEGACY_AGGREGATE_SLUGS[slug]
            if is_standalone_inventory_type(ct)
        ]
    ct = canonical_from_api_path(path)
    return [ct] if ct else []


def inventory_route_catalog() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for slug, ct in sorted(LEGACY_SLUG_TO_CANONICAL.items(), key=lambda item: item[1]):
        if ct in seen or not is_standalone_inventory_type(ct):
            continue
        seen.add(ct)
        rows.append({
            "canonical_type": ct,
            "api_path": canonical_api_path(ct),
            "legacy_api_path": legacy_slug_api_path(slug),
            "legacy_slug": slug,
        })
    return rows
