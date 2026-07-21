"""Filter governance / region-approval rows out of cost-driving signal payloads."""

from __future__ import annotations

import re
from typing import Any

_GOVERNANCE_FACT_KEYS = frozenset({
    "region_approved",
    "regionapproved",
    "region_classification",
    "regionclassification",
    "recommended_region",
    "recommendedregion",
    "recommendedregiondisplay",
    "current_region",
    "currentregion",
    "region_move_allowed",
    "regionmoveallowed",
    "region_migration_required",
    "regionmigrationrequired",
})

_GOVERNANCE_LABEL = re.compile(
    r"region approval|approve region|approved region|unapproved region|"
    r"region govern|data residency|region migration|recommended region",
    re.I,
)
_GOVERNANCE_RULE = re.compile(
    r"unapproved_region|region_governance|governance_region|best_unapproved",
    re.I,
)
_GOVERNANCE_ITEM_ID = re.compile(
    r"region-classification|recommended-region|region-migration|region_approval",
    re.I,
)


def is_governance_cost_signal(item: dict[str, Any] | None) -> bool:
    if not item:
        return False

    fact_key = str(item.get("fact_key") or "").lower()
    label = str(item.get("label") or "")
    item_id = str(item.get("id") or "")
    rules = " ".join(item.get("rules") or [])

    if fact_key in _GOVERNANCE_FACT_KEYS:
        return True
    if item.get("kind") == "region":
        return True
    if _GOVERNANCE_LABEL.search(label):
        return True
    if _GOVERNANCE_RULE.search(rules):
        return True
    if _GOVERNANCE_ITEM_ID.search(item_id):
        return True
    return False


def filter_cost_driving_metrics(metrics: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [row for row in (metrics or []) if not is_governance_cost_signal(row)]


def filter_cost_drivers(drivers: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [row for row in (drivers or []) if not is_governance_cost_signal(row)]


def filter_metrics_payload_for_cost_signals(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Strip governance/region rows from a unified metrics API payload."""
    if not payload:
        return {}

    out = dict(payload)
    out["metrics"] = filter_cost_driving_metrics(payload.get("metrics"))
    out["derived"] = filter_cost_driving_metrics(payload.get("derived"))

    mapping = payload.get("cost_driver_mapping") or {}
    if mapping:
        out["cost_driver_mapping"] = {
            **mapping,
            "cost_drivers": filter_cost_drivers(mapping.get("cost_drivers")),
        }
    return out
