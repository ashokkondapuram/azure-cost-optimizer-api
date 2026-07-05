"""Per-component Azure inventory sync intervals and rotation."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from app.optimizer.component_map import ANALYSIS_BATCHES, sync_types_for_component

# Components with their own inventory fetch (Commitments reuses VMs; Budgets are separate).
SKIP_COMPONENTS = frozenset({"Commitments", "Budgets"})

# Recommended refresh cadence by churn / API cost.
FAST_COMPONENTS = frozenset({
    "Virtual Machines",
    "Virtual Machine Scale Sets",
    "Managed Disks",
    "Disk Snapshots",
    "AKS",
})
STANDARD_COMPONENTS = frozenset({
    "App Service",
    "Storage Accounts",
    "SQL Database",
    "PostgreSQL",
    "Cosmos DB",
    "Redis Cache",
    "Container Registry",
    "Key Vault",
})

DEFAULT_INTERVALS_MINUTES: dict[str, int] = {
    "fast": 15,
    "standard": 30,
    "slow": 60,
}


def syncable_components() -> list[str]:
    return [b["component"] for b in ANALYSIS_BATCHES if b["component"] not in SKIP_COMPONENTS]


def _tier_for_component(component: str) -> str:
    if component in FAST_COMPONENTS:
        return "fast"
    if component in STANDARD_COMPONENTS:
        return "standard"
    return "slow"


def interval_minutes_for_component(component: str) -> int:
    """Return sync interval in minutes for a component (env override supported)."""
    per_component_key = f"SCHEDULED_SYNC_INTERVAL_{component.upper().replace(' ', '_')}_MINUTES"
    raw = os.getenv(per_component_key)
    if raw is not None and raw.strip():
        return max(5, int(float(raw.strip())))

    tier = _tier_for_component(component)
    tier_env = {
        "fast": "SCHEDULED_SYNC_INTERVAL_FAST_MINUTES",
        "standard": "SCHEDULED_SYNC_INTERVAL_STANDARD_MINUTES",
        "slow": "SCHEDULED_SYNC_INTERVAL_SLOW_MINUTES",
    }[tier]
    default = DEFAULT_INTERVALS_MINUTES[tier]
    if os.getenv(tier_env) is not None:
        return max(5, int(float(os.getenv(tier_env, str(default)))))
    return default


def component_sync_catalog() -> list[dict[str, Any]]:
    return [
        {
            "component": component,
            "tier": _tier_for_component(component),
            "interval_minutes": interval_minutes_for_component(component),
            "resource_types": sync_types_for_component(component),
        }
        for component in syncable_components()
    ]


def pick_next_due_component(
    last_sync_at: dict[str, datetime],
    *,
    now: datetime | None = None,
) -> tuple[str | None, float]:
    """
    Return the most overdue component and its overdue seconds (>= 0 when due).
    Returns (None, negative) when nothing is due yet.
    """
    now = now or datetime.now(timezone.utc)
    best_component: str | None = None
    best_overdue = float("-inf")

    for component in syncable_components():
        interval_sec = interval_minutes_for_component(component) * 60.0
        last = last_sync_at.get(component)
        if last is None:
            return component, interval_sec
        elapsed = (now - last).total_seconds()
        overdue = elapsed - interval_sec
        if overdue > best_overdue:
            best_overdue = overdue
            best_component = component

    if best_component is None or best_overdue < 0:
        return None, best_overdue
    return best_component, best_overdue
