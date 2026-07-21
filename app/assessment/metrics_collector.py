"""Assessment-driven metrics collection plan for pipeline workers."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.assessment.catalog import get_assessment_for_arm_type
from app.assessment.spec import (
    assessment_metadata,
    monitor_metric_names,
    required_metric_keys,
)
from app.pipeline.store import resources_by_canonical_for_metrics
from app.resource_type_map import arm_provider_type
from app.focus_mapping import normalize_arm_id


def _filter_metrics_grouped(
    grouped: dict[str, list[dict[str, Any]]],
    *,
    canonical_types: set[str] | frozenset[str] | None = None,
    arm_ids: set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if not canonical_types and not arm_ids:
        return grouped
    allowed_types = {t.strip().lower() for t in canonical_types} if canonical_types else None
    allowed_arms = (
        {normalize_arm_id(rid).lower() for rid in arm_ids if normalize_arm_id(rid)}
        if arm_ids
        else None
    )
    filtered: dict[str, list[dict[str, Any]]] = {}
    for canonical, items in grouped.items():
        canon_key = (canonical or "").strip().lower()
        if allowed_types and canon_key not in allowed_types:
            continue
        scoped_items = items
        if allowed_arms:
            scoped_items = [
                item
                for item in items
                if normalize_arm_id(item.get("id") or "").lower() in allowed_arms
            ]
        if scoped_items:
            filtered[canon_key] = scoped_items
    return filtered


def build_assessment_metrics_plan(
    db: Session,
    subscription_id: str,
    *,
    canonical_types: set[str] | frozenset[str] | list[str] | None = None,
    arm_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Group indexed inventory and attach assessment JSON metric requirements."""
    grouped = resources_by_canonical_for_metrics(db, subscription_id)
    type_filter = (
        {t.strip().lower() for t in canonical_types}
        if canonical_types
        else None
    )
    grouped = _filter_metrics_grouped(
        grouped,
        canonical_types=type_filter,
        arm_ids=arm_ids,
    )
    metric_names_by_canonical: dict[str, tuple[str, ...]] = {}
    required_keys_by_canonical: dict[str, list[str]] = {}
    assessment_by_canonical: dict[str, dict[str, Any]] = {}

    for canonical, items in grouped.items():
        if not items:
            continue
        arm_type = arm_provider_type(items[0].get("id") or "") or ""
        assessment = get_assessment_for_arm_type(arm_type)
        if not assessment:
            continue
        metric_names_by_canonical[canonical] = monitor_metric_names(assessment)
        required_keys_by_canonical[canonical] = required_metric_keys(assessment)
        assessment_by_canonical[canonical] = assessment_metadata(assessment)

    return {
        "grouped": grouped,
        "metric_names_by_canonical": metric_names_by_canonical,
        "required_keys_by_canonical": required_keys_by_canonical,
        "assessment_by_canonical": assessment_by_canonical,
    }
