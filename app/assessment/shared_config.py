"""Load shared assessment JSON policy files from data/."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.assessment.catalog import assessment_data_dir


def _load_json(name: str) -> dict[str, Any]:
    path = assessment_data_dir() / name
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def load_region_governance_policy() -> dict[str, Any]:
    return _load_json("region-governance-policy.json")


@lru_cache(maxsize=1)
def load_pillar_triggers() -> dict[str, Any]:
    return _load_json("assessment-pillar-triggers.json")


def merge_region_governance_policy(assessment: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge global region policy with per-assessment regionGovernance overrides."""
    policy = dict(load_region_governance_policy())
    block = (assessment or {}).get("regionGovernance") or {}
    if not block:
        return policy

    merged = dict(policy)
    classifications = dict(policy.get("classifications") or {})
    if block.get("approvedRegions"):
        approved = dict(classifications.get("approved") or {})
        approved["regions"] = list(block["approvedRegions"])
        classifications["approved"] = approved
    if block.get("conditionalRegions"):
        conditional = dict(classifications.get("conditional") or {})
        conditional["regions"] = list(block["conditionalRegions"])
        classifications["conditional"] = conditional
    if block.get("blockedRegions"):
        blocked = dict(classifications.get("blocked") or {})
        blocked["regions"] = list(block["blockedRegions"])
        classifications["blocked"] = blocked
    merged["classifications"] = classifications

    if block.get("primaryApprovedRegion"):
        merged["primary_approved_region"] = block["primaryApprovedRegion"]
    if block.get("secondaryApprovedRegion"):
        merged["secondary_approved_region"] = block["secondaryApprovedRegion"]
    if block.get("recommendedTargetRegion"):
        targets = dict(merged.get("recommended_target") or {})
        targets["production"] = block["recommendedTargetRegion"]
        targets["non_production"] = block["recommendedTargetRegion"]
        merged["recommended_target"] = targets
    return merged


def merge_pillar_triggers(assessment: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge global pillar triggers with per-assessment pillarTriggers metadata."""
    triggers = dict(load_pillar_triggers())
    block = (assessment or {}).get("pillarTriggers") or {}
    if not block:
        return triggers
    merged = dict(triggers)
    resource_type = block.get("resourceType")
    if resource_type:
        overrides = dict(merged.get("service_overrides") or {})
        entry = dict(overrides.get(resource_type) or {})
        if block.get("metric_thresholds"):
            entry["metric_thresholds"] = {
                **(entry.get("metric_thresholds") or {}),
                **block["metric_thresholds"],
            }
        overrides[resource_type] = entry
        merged["service_overrides"] = overrides
    return merged


def clear_shared_config_cache() -> None:
    load_region_governance_policy.cache_clear()
    load_pillar_triggers.cache_clear()
