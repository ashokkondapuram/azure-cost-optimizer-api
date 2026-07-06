"""Tag Compliance — report which resources are missing required tags.

Scans OptimizationFinding rows whose rule_id starts with 'TAG_' or whose
evidence contains a 'missing_tags' key.  Also exposes a summary counter.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import OptimizationFinding

# Tags that are considered mandatory.  Override via DB settings in future.
DEFAULT_REQUIRED_TAGS = ["environment", "owner", "cost-center", "project"]


def get_tag_compliance(
    db: Session,
    subscription_id: str | None = None,
    required_tags: list[str] | None = None,
) -> dict[str, Any]:
    required = required_tags or DEFAULT_REQUIRED_TAGS

    q = db.query(OptimizationFinding).filter(
        OptimizationFinding.rule_id.like("TAG_%")
    )
    if subscription_id:
        q = q.filter(OptimizationFinding.subscription_id == subscription_id)

    findings = q.order_by(OptimizationFinding.created_at.desc()).limit(500).all()

    non_compliant: list[dict] = []
    tag_miss_counts: dict[str, int] = {t: 0 for t in required}

    for f in findings:
        evidence = f.evidence or {}
        missing = evidence.get("missing_tags") or []
        # Fall back: if rule_id encodes a tag name, extract it.
        if not missing and f.rule_id and "_" in f.rule_id:
            tag_name = f.rule_id.split("_", 1)[1].lower().replace("_", "-")
            missing = [tag_name]

        for t in missing:
            if t in tag_miss_counts:
                tag_miss_counts[t] += 1

        non_compliant.append(
            {
                "resource_id": f.resource_id,
                "resource_name": f.resource_name,
                "resource_type": f.resource_type,
                "resource_group": f.resource_group,
                "missing_tags": missing,
                "status": f.status,
                "severity": f.severity,
            }
        )

    total_resources = db.query(OptimizationFinding.resource_id).distinct().count()
    compliant_count = max(0, total_resources - len({r["resource_id"] for r in non_compliant}))

    return {
        "required_tags": required,
        "summary": {
            "total_resources": total_resources,
            "non_compliant": len(non_compliant),
            "compliant": compliant_count,
            "compliance_pct": round(
                100 * compliant_count / max(total_resources, 1), 1
            ),
        },
        "tag_miss_counts": tag_miss_counts,
        "resources": non_compliant,
    }
