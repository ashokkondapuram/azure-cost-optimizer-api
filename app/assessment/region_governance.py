"""Region classification and recommendation from region-governance-policy.json."""

from __future__ import annotations

from typing import Any

from app.assessment.shared_config import merge_region_governance_policy


def normalize_region(location: str | None) -> str:
    return (location or "").strip().lower().replace(" ", "")


def _region_lists(policy: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    classifications = policy.get("classifications") or {}
    approved = {normalize_region(r) for r in (classifications.get("approved") or {}).get("regions") or []}
    conditional = {normalize_region(r) for r in (classifications.get("conditional") or {}).get("regions") or []}
    blocked = {normalize_region(r) for r in (classifications.get("blocked") or {}).get("regions") or []}
    return approved, conditional, blocked


def classify_region(
    location: str | None,
    policy: dict[str, Any] | None = None,
    *,
    assessment: dict[str, Any] | None = None,
) -> str:
    region = normalize_region(location)
    if not region:
        return "unclassified"
    policy = policy or merge_region_governance_policy(assessment)
    approved, conditional, blocked = _region_lists(policy)
    if region in blocked:
        return "blocked"
    if region in approved:
        return "approved"
    if region in conditional:
        return "conditional"
    return "unclassified"


def is_region_approved(
    location: str | None,
    policy: dict[str, Any] | None = None,
    *,
    assessment: dict[str, Any] | None = None,
) -> bool:
    return classify_region(location, policy, assessment=assessment) == "approved"


def service_override(
    resource_type: str | None,
    policy: dict[str, Any] | None = None,
    *,
    assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = policy or merge_region_governance_policy(assessment)
    overrides = policy.get("service_overrides") or {}
    key = (resource_type or "").strip()
    if key in overrides:
        return dict(overrides[key])
    return {}


def recommended_region(
    location: str | None,
    *,
    resource_type: str | None = None,
    is_production: bool = False,
    policy: dict[str, Any] | None = None,
    assessment: dict[str, Any] | None = None,
) -> str:
    policy = policy or merge_region_governance_policy(assessment)
    override = service_override(resource_type, policy, assessment=assessment)
    if override.get("recommended_region"):
        return normalize_region(str(override["recommended_region"]))
    targets = policy.get("recommended_target") or {}
    if is_production:
        return normalize_region(targets.get("production") or policy.get("primary_approved_region") or "canadacentral")
    return normalize_region(targets.get("non_production") or policy.get("primary_approved_region") or "canadacentral")


def region_move_allowed(
    resource_type: str | None,
    policy: dict[str, Any] | None = None,
    *,
    assessment: dict[str, Any] | None = None,
) -> bool:
    override = service_override(resource_type, policy, assessment=assessment)
    if "region_move_allowed" in override:
        return bool(override["region_move_allowed"])
    return False


def region_display_name(
    location: str | None,
    policy: dict[str, Any] | None = None,
    *,
    assessment: dict[str, Any] | None = None,
) -> str:
    region = normalize_region(location)
    policy = policy or merge_region_governance_policy(assessment)
    catalog = policy.get("azure_region_catalog") or {}
    entry = catalog.get(region) or {}
    return str(entry.get("display_name") or region or "unknown")


def compute_region_signals(
    record: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
    assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = policy or merge_region_governance_policy(assessment)
    resource = record.get("resource") or {}
    location = record.get("location") or resource.get("location")
    resource_type = record.get("resource_type") or resource.get("type")
    tags = record.get("tags") or {}
    env = (tags.get("Environment") or tags.get("environment") or "").strip().lower()
    is_prod = env in {"prod", "production", "prd"}

    classification = classify_region(location, policy, assessment=assessment)
    approved = classification == "approved"
    recommended = recommended_region(
        location,
        resource_type=resource_type,
        is_production=is_prod,
        policy=policy,
        assessment=assessment,
    )

    return {
        "currentRegion": normalize_region(location),
        "regionClassification": classification,
        "regionApproved": approved,
        "recommendedRegion": recommended,
        "recommendedRegionDisplay": region_display_name(recommended, policy, assessment=assessment),
        "regionMoveAllowed": region_move_allowed(resource_type, policy, assessment=assessment),
        "regionMigrationRequired": bool(service_override(resource_type, policy, assessment=assessment).get("migration_required")),
    }
