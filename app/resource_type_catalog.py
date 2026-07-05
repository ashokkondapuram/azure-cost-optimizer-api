"""Resource type catalog for cost filtering UI (grouped canonical types)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.optimizer.component_map import COMPONENT_RESOURCE_TYPES
from app.resource_type_map import ARM_PROVIDER_TO_INTERNAL

_CATEGORY_ORDER = [
    "Compute",
    "Containers",
    "Storage",
    "Network",
    "Database",
    "App Service",
    "Security",
    "Monitoring",
    "Integration",
    "Messaging",
    "Analytics",
    "Backup",
    "Automation",
    "Search",
    "Other",
]

_PREFIX_TO_CATEGORY = {
    "compute": "Compute",
    "containers": "Containers",
    "storage": "Storage",
    "network": "Network",
    "database": "Database",
    "appservice": "App Service",
    "security": "Security",
    "monitoring": "Monitoring",
    "integration": "Integration",
    "messaging": "Messaging",
    "analytics": "Analytics",
    "backup": "Backup",
    "automation": "Automation",
    "search": "Search",
}


def _canonical_label(canonical: str) -> str:
    for label, types in COMPONENT_RESOURCE_TYPES.items():
        if canonical in types:
            return label
    parts = canonical.split("/")
    if len(parts) == 2:
        return parts[1].replace("_", " ").title()
    return canonical


@lru_cache(maxsize=1)
def all_canonical_resource_types() -> tuple[str, ...]:
    from app.resource_type_map import SERVICE_NAME_TO_INTERNAL

    types = set(ARM_PROVIDER_TO_INTERNAL.values())
    types.update(SERVICE_NAME_TO_INTERNAL.values())
    return tuple(sorted(types))


def expand_resource_type_filter(values: list[str] | None) -> set[str] | None:
    """Expand category prefixes (e.g. compute) and canonical ids; None = all types."""
    if not values:
        return None
    all_types = set(all_canonical_resource_types())
    expanded: set[str] = set()
    for raw in values:
        token = (raw or "").strip().lower()
        if not token:
            continue
        if token in all_types:
            expanded.add(token)
            continue
        if "/" not in token:
            prefix = f"{token}/"
            matched = {t for t in all_types if t.startswith(prefix)}
            if matched:
                expanded.update(matched)
                continue
        expanded.add(token)
    return expanded or None


def parse_resource_types_param(raw: str | None) -> list[str] | None:
    if not raw or not str(raw).strip():
        return None
    parts = [p.strip() for p in str(raw).replace(";", ",").split(",") if p.strip()]
    return parts or None


def resource_types_catalog() -> dict[str, Any]:
    """Grouped resource types for filter UI."""
    groups: dict[str, list[dict[str, str]]] = {c: [] for c in _CATEGORY_ORDER}
    seen: set[str] = set()
    for canonical in all_canonical_resource_types():
        if canonical in seen:
            continue
        seen.add(canonical)
        prefix = canonical.split("/")[0] if "/" in canonical else "other"
        category = _PREFIX_TO_CATEGORY.get(prefix, "Other")
        groups.setdefault(category, []).append({
            "canonical": canonical,
            "label": _canonical_label(canonical),
        })
    ordered_groups = []
    for category in _CATEGORY_ORDER:
        items = sorted(groups.get(category) or [], key=lambda row: row["label"].lower())
        if items:
            ordered_groups.append({
                "category": category,
                "types": items,
            })
    flat = [row for group in ordered_groups for row in group["types"]]
    return {
        "categories": ordered_groups,
        "types": flat,
        "count": len(flat),
    }
