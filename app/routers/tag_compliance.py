"""Tag compliance — score resource tagging coverage and flag untagged resources."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ResourceSnapshot

router = APIRouter(prefix="/tag-compliance", tags=["Tag Compliance"])

# Default required tags — configurable via query param override
_DEFAULT_REQUIRED_TAGS = ["environment", "owner", "cost-center"]


def _normalize(sub: str) -> str:
    return (sub or "").strip().lower()


def _parse_tags(tags_raw: Any) -> dict[str, str]:
    if isinstance(tags_raw, dict):
        return {k.lower(): v for k, v in tags_raw.items()}
    return {}


@router.get("/score/{subscription_id}")
def tag_compliance_score(
    subscription_id: str,
    required_tags: list[str] = Query(_DEFAULT_REQUIRED_TAGS, description="Required tag key names (case-insensitive)"),
    resource_group: str | None = Query(None, description="Filter to a specific resource group"),
    resource_type: str | None = Query(None, description="Filter to a specific resource type"),
    db: Session = Depends(get_db),
) -> dict:
    """Compute tag coverage score and list non-compliant resources."""
    sub = _normalize(subscription_id)
    required = [t.lower() for t in required_tags]

    query = db.query(ResourceSnapshot).filter(ResourceSnapshot.subscription_id == sub)
    if resource_group:
        query = query.filter(ResourceSnapshot.resource_group == resource_group.lower())
    if resource_type:
        query = query.filter(ResourceSnapshot.resource_type.ilike(f"%{resource_type}%"))

    resources = query.all()
    if not resources:
        return {
            "subscription_id": subscription_id,
            "score_pct": None,
            "message": "No resources found. Run a resource sync first.",
            "source": "database",
        }

    total = len(resources)
    fully_compliant = 0
    non_compliant: list[dict] = []
    tag_coverage: dict[str, int] = {t: 0 for t in required}

    for res in resources:
        tags = _parse_tags(res.tags)
        missing = [t for t in required if t not in tags]
        present = [t for t in required if t in tags]
        for t in present:
            tag_coverage[t] += 1
        if not missing:
            fully_compliant += 1
        else:
            non_compliant.append({
                "resource_id": res.resource_id,
                "resource_name": res.name,
                "resource_type": res.resource_type,
                "resource_group": res.resource_group,
                "missing_tags": missing,
                "present_tags": list(tags.keys()),
                "compliance_pct": round((len(present) / len(required)) * 100, 1) if required else 100.0,
            })

    score = round((fully_compliant / total) * 100, 1) if total > 0 else 0.0
    tag_coverage_pct = {
        t: round((count / total) * 100, 1) for t, count in tag_coverage.items()
    }

    return {
        "subscription_id": subscription_id,
        "total_resources": total,
        "fully_compliant": fully_compliant,
        "non_compliant_count": len(non_compliant),
        "score_pct": score,
        "required_tags": required,
        "tag_coverage_pct": tag_coverage_pct,
        "non_compliant_resources": non_compliant[:100],
        "source": "database",
    }


@router.get("/groups/{subscription_id}")
def tag_compliance_by_resource_group(
    subscription_id: str,
    required_tags: list[str] = Query(_DEFAULT_REQUIRED_TAGS),
    db: Session = Depends(get_db),
) -> dict:
    """Summarise tag compliance per resource group."""
    sub = _normalize(subscription_id)
    required = [t.lower() for t in required_tags]

    resources = db.query(ResourceSnapshot).filter(ResourceSnapshot.subscription_id == sub).all()
    if not resources:
        return {"subscription_id": subscription_id, "groups": [], "source": "database"}

    groups: dict[str, dict] = {}
    for res in resources:
        rg = (res.resource_group or "unknown").lower()
        g = groups.setdefault(rg, {"total": 0, "compliant": 0, "resource_group": rg})
        g["total"] += 1
        tags = _parse_tags(res.tags)
        if all(t in tags for t in required):
            g["compliant"] += 1

    result = [
        {
            **g,
            "score_pct": round((g["compliant"] / g["total"]) * 100, 1) if g["total"] else 0.0,
        }
        for g in groups.values()
    ]
    result.sort(key=lambda x: x["score_pct"])
    return {
        "subscription_id": subscription_id,
        "required_tags": required,
        "groups": result,
        "source": "database",
    }
