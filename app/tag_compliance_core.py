"""Shared tag compliance calculations for API routes."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import ResourceSnapshot
from app.utils import parse_tags_json

DEFAULT_REQUIRED_TAGS = ["environment", "owner", "cost-center"]


def _normalize_sub(subscription_id: str) -> str:
    return (subscription_id or "").strip().lower()


def _base_query(db: Session, subscription_id: str):
    sub = _normalize_sub(subscription_id)
    return (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
            ResourceSnapshot.is_cost_export_only.is_(False),
        )
    )


def compute_tag_compliance(
    db: Session,
    subscription_id: str,
    *,
    required_tags: list[str] | None = None,
    resource_group: str | None = None,
    resource_type: str | None = None,
    limit: int = 2000,
) -> dict[str, Any]:
    """Scan active inventory snapshots and compute tag compliance aggregates."""
    required = [t.strip().lower() for t in (required_tags or DEFAULT_REQUIRED_TAGS) if t.strip()]
    query = _base_query(db, subscription_id)
    if resource_group:
        query = query.filter(ResourceSnapshot.resource_group == resource_group.strip().lower())
    if resource_type:
        query = query.filter(ResourceSnapshot.resource_type.ilike(f"%{resource_type.strip()}%"))

    resources = query.all()
    if not resources:
        return {
            "subscription_id": subscription_id,
            "score_pct": None,
            "message": "No active resources found. Sync inventory first.",
            "total_resources": 0,
            "fully_compliant": 0,
            "non_compliant_count": 0,
            "required_tags": required,
            "tag_coverage_pct": {},
            "tag_missing_counts": {},
            "by_resource_type": [],
            "groups": [],
            "non_compliant_resources": [],
            "items_returned": 0,
            "items_truncated": False,
            "source": "database",
        }

    total = len(resources)
    fully_compliant = 0
    non_compliant: list[dict[str, Any]] = []
    tag_present_counts: dict[str, int] = {t: 0 for t in required}
    tag_missing_counts: dict[str, int] = {t: 0 for t in required}
    type_stats: dict[str, dict[str, int]] = {}
    group_stats: dict[str, dict[str, Any]] = {}

    for res in resources:
        tags = parse_tags_json(res.tags_json)
        missing = [t for t in required if t not in tags]
        present = [t for t in required if t in tags]
        for tag in present:
            tag_present_counts[tag] += 1
        for tag in missing:
            tag_missing_counts[tag] += 1

        rtype = res.resource_type or "(unknown)"
        type_bucket = type_stats.setdefault(rtype, {"total": 0, "compliant": 0})
        type_bucket["total"] += 1

        rg = (res.resource_group or "unknown").lower()
        group_bucket = group_stats.setdefault(
            rg,
            {"resource_group": rg, "total": 0, "compliant": 0},
        )
        group_bucket["total"] += 1

        if not missing:
            fully_compliant += 1
            type_bucket["compliant"] += 1
            group_bucket["compliant"] += 1
        else:
            non_compliant.append({
                "resource_id": res.resource_id,
                "resource_name": res.resource_name,
                "resource_type": res.resource_type,
                "resource_group": res.resource_group,
                "missing_tags": missing,
                "present_tags": sorted(tags.keys()),
                "compliance_pct": round((len(present) / len(required)) * 100, 1) if required else 100.0,
            })

    non_compliant.sort(key=lambda row: (row["compliance_pct"], row["resource_name"] or ""))
    page = non_compliant[:limit]

    score = round((fully_compliant / total) * 100, 1) if total > 0 else 0.0
    tag_coverage_pct = {
        t: round((tag_present_counts[t] / total) * 100, 1) for t in required
    }

    by_resource_type = [
        {
            "resource_type": rtype,
            "total": stats["total"],
            "compliant": stats["compliant"],
            "non_compliant": stats["total"] - stats["compliant"],
            "score_pct": round((stats["compliant"] / stats["total"]) * 100, 1) if stats["total"] else 0.0,
        }
        for rtype, stats in sorted(
            type_stats.items(),
            key=lambda item: (item[1]["total"] - item[1]["compliant"], -item[1]["total"]),
            reverse=True,
        )
    ]

    groups = [
        {
            **g,
            "score_pct": round((g["compliant"] / g["total"]) * 100, 1) if g["total"] else 0.0,
        }
        for g in group_stats.values()
    ]
    groups.sort(key=lambda row: row["score_pct"])

    return {
        "subscription_id": subscription_id,
        "total_resources": total,
        "fully_compliant": fully_compliant,
        "non_compliant_count": len(non_compliant),
        "score_pct": score,
        "required_tags": required,
        "tag_coverage_pct": tag_coverage_pct,
        "tag_missing_counts": tag_missing_counts,
        "by_resource_type": by_resource_type,
        "groups": groups,
        "non_compliant_resources": page,
        "items_returned": len(page),
        "items_truncated": len(page) < len(non_compliant),
        "source": "database",
    }
