"""Finding activity / audit trail API."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.finding_activity import list_finding_activity, log_activity_entry
from app.models import OptimizationFinding
from app.user_auth import require_authenticated_user
from app.validators import ensure_subscription_known, require_subscription_id

router = APIRouter(prefix="/activity", tags=["Activity"])


class ActivityLogIn(BaseModel):
    finding_id: str
    subscription_id: str
    action: str = Field(default="note", max_length=64)
    note: Optional[str] = None
    from_status: Optional[str] = None
    to_status: Optional[str] = None


def _load_finding(db: Session, *, finding_id: str, subscription_id: str) -> OptimizationFinding:
    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    finding = db.query(OptimizationFinding).filter(OptimizationFinding.id == finding_id).first()
    if not finding or (finding.subscription_id or "").lower() != sub:
        raise HTTPException(404, "Finding not found")
    return finding


@router.get("/finding/{finding_id}", summary="Activity log for a finding")
def get_finding_activity(
    finding_id: str = Path(...),
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    _load_finding(db, finding_id=finding_id, subscription_id=subscription_id)
    return {"items": list_finding_activity(db, finding_id=finding_id, limit=limit)}


@router.post("/log", summary="Record finding activity", status_code=201)
def post_activity_log(
    request: Request,
    body: ActivityLogIn,
    db: Session = Depends(get_db),
):
    user = require_authenticated_user(request)
    finding = _load_finding(db, finding_id=body.finding_id, subscription_id=body.subscription_id)
    entry = log_activity_entry(
        db,
        finding_id=finding.id,
        subscription_id=finding.subscription_id,
        action=body.action,
        from_status=body.from_status,
        to_status=body.to_status,
        note=body.note,
        user=user,
    )
    db.commit()
    from app.finding_activity import serialize_activity

    return serialize_activity(entry)
