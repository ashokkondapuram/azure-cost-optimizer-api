"""Tag compliance — score resource tagging coverage and flag untagged resources."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.tag_compliance_core import DEFAULT_REQUIRED_TAGS, compute_tag_compliance

router = APIRouter(prefix="/tag-compliance", tags=["Tag Compliance"])


@router.get("/score/{subscription_id}")
def tag_compliance_score(
    subscription_id: str,
    required_tags: list[str] = Query(
        DEFAULT_REQUIRED_TAGS,
        description="Required tag key names (case-insensitive)",
    ),
    resource_group: str | None = Query(None, description="Filter to a specific resource group"),
    resource_type: str | None = Query(None, description="Filter to a specific resource type"),
    limit: int = Query(2000, ge=1, le=5000, description="Max non-compliant resources returned"),
    db: Session = Depends(get_db),
) -> dict:
    """Compute tag coverage score and list non-compliant resources."""
    result = compute_tag_compliance(
        db,
        subscription_id,
        required_tags=required_tags,
        resource_group=resource_group,
        resource_type=resource_type,
        limit=limit,
    )
    return result


@router.get("/groups/{subscription_id}")
def tag_compliance_by_resource_group(
    subscription_id: str,
    required_tags: list[str] = Query(DEFAULT_REQUIRED_TAGS),
    db: Session = Depends(get_db),
) -> dict:
    """Summarise tag compliance per resource group."""
    result = compute_tag_compliance(db, subscription_id, required_tags=required_tags, limit=0)
    return {
        "subscription_id": subscription_id,
        "required_tags": result.get("required_tags", []),
        "groups": result.get("groups", []),
        "source": "database",
    }
