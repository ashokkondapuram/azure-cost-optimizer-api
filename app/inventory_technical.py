"""Extract technical configuration facts from Azure-synced inventory (not cost export)."""

from __future__ import annotations

from typing import Any

from app.resource_type_map import arm_provider_type
from app.resources import extract_technical_facts as _extract_from_specs


def technical_facts_from_inventory_row(row: dict[str, Any] | None) -> dict[str, Any]:
    """
    Build technical (non-cost) facts from a resource_snapshots row dict.
    Returns empty dict for cost-export-only stubs without Azure inventory.
    """
    return _extract_from_specs(row)


def arm_resource_type_for_finding(resource_id: str, fallback: str = "") -> str:
    """Prefer ARM provider/type parsed from resource ID over canonical or billing labels."""
    arm = arm_provider_type(resource_id)
    if arm:
        return arm
    fb = (fallback or "").strip()
    if fb.startswith("microsoft.") or "/" in fb and not fb.startswith(
        ("compute/", "database/", "network/", "monitoring/", "integration/", "messaging/", "analytics/")
    ):
        return fb
    return arm or fb
