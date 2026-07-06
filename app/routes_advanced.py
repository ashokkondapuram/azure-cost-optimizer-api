"""Advanced tools — FastAPI route handlers.

Imported and included in main.py via:

    from app.routes_advanced import router as advanced_router
    app.include_router(advanced_router)

Endpoints
---------
GET  /api/waste-heatmap
GET  /api/tag-compliance
GET  /api/auto-scheduler
GET  /api/notifications
POST /api/notifications
PATCH /api/notifications/{channel_id}
DELETE /api/notifications/{channel_id}
GET  /api/anomaly-detector
GET  /api/timeline
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.user_auth import require_authenticated_user
from app.waste_heatmap import get_waste_heatmap
from app.tag_compliance import get_tag_compliance
from app.auto_scheduler_api import get_scheduler_status
from app.notification_channels import (
    add_channel,
    delete_channel,
    get_notification_summary,
    update_channel,
)
from app.cost_anomaly_detector import detect_cost_anomalies
from app.optimization_timeline import get_optimization_timeline

router = APIRouter(prefix="/api", tags=["Advanced Tools"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class NotificationChannelIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    type: str = Field(..., description="email | slack | webhook | teams")
    destination: str = Field(..., min_length=1, max_length=512,
                             description="Email address, webhook URL, or Teams URL")
    enabled: bool = True
    events: list[str] = Field(
        default_factory=lambda: ["anomaly", "high_severity_finding"],
        description="Event types that trigger this channel",
    )


class NotificationChannelUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    type: Optional[str] = None
    destination: Optional[str] = Field(None, max_length=512)
    enabled: Optional[bool] = None
    events: Optional[list[str]] = None


# ── Waste Heatmap ─────────────────────────────────────────────────────────────

@router.get(
    "/waste-heatmap",
    summary="Waste heatmap grouped by resource group and resource type",
)
def waste_heatmap(
    request: Request,
    subscription_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    require_authenticated_user(request)
    return get_waste_heatmap(db, subscription_id=subscription_id)


# ── Tag Compliance ────────────────────────────────────────────────────────────

@router.get(
    "/tag-compliance",
    summary="Tag compliance report — resources missing required tags",
)
def tag_compliance(
    request: Request,
    subscription_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    require_authenticated_user(request)
    return get_tag_compliance(db, subscription_id=subscription_id)


# ── Auto Scheduler ────────────────────────────────────────────────────────────

@router.get(
    "/auto-scheduler",
    summary="Scheduler status — recent jobs, runs, and pending work",
)
def auto_scheduler(
    request: Request,
    subscription_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    require_authenticated_user(request)
    return get_scheduler_status(db, subscription_id=subscription_id)


# ── Notification Channels ─────────────────────────────────────────────────────

@router.get(
    "/notifications",
    summary="List notification channels and summary stats",
)
def list_notifications(
    request: Request,
    db: Session = Depends(get_db),
):
    require_authenticated_user(request)
    return get_notification_summary(db)


@router.post(
    "/notifications",
    summary="Create a notification channel",
    status_code=201,
)
def create_notification(
    request: Request,
    body: NotificationChannelIn,
    db: Session = Depends(get_db),
):
    require_authenticated_user(request)
    channel = add_channel(db, body.model_dump())
    return {"status": "created", "channel": channel}


@router.patch(
    "/notifications/{channel_id}",
    summary="Update a notification channel",
)
def update_notification(
    request: Request,
    channel_id: str = Path(...),
    body: NotificationChannelUpdate = Body(...),
    db: Session = Depends(get_db),
):
    require_authenticated_user(request)
    updated = update_channel(db, channel_id, body.model_dump(exclude_none=True))
    if updated is None:
        raise HTTPException(404, f"Channel {channel_id!r} not found")
    return {"status": "updated", "channel": updated}


@router.delete(
    "/notifications/{channel_id}",
    summary="Delete a notification channel",
)
def delete_notification(
    request: Request,
    channel_id: str = Path(...),
    db: Session = Depends(get_db),
):
    require_authenticated_user(request)
    removed = delete_channel(db, channel_id)
    if not removed:
        raise HTTPException(404, f"Channel {channel_id!r} not found")
    return {"status": "deleted", "channel_id": channel_id}


# ── Cost Anomaly Detector ─────────────────────────────────────────────────────

@router.get(
    "/anomaly-detector",
    summary="Detect cost anomalies using z-score over daily cost data",
)
def anomaly_detector(
    request: Request,
    subscription_id: Optional[str] = Query(None),
    lookback_days: int = Query(30, ge=7, le=90, description="Days of history to analyse"),
    zscore_threshold: float = Query(2.0, ge=1.0, le=5.0,
                                    description="Z-score threshold for flagging an anomaly"),
    db: Session = Depends(get_db),
):
    require_authenticated_user(request)
    return detect_cost_anomalies(
        db,
        subscription_id=subscription_id,
        lookback_days=lookback_days,
        zscore_threshold=zscore_threshold,
    )


# ── Optimization Timeline ─────────────────────────────────────────────────────

@router.get(
    "/timeline",
    summary="Chronological history of optimization runs with top findings",
)
def optimization_timeline(
    request: Request,
    subscription_id: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=100, description="Max number of runs to return"),
    db: Session = Depends(get_db),
):
    require_authenticated_user(request)
    return get_optimization_timeline(db, subscription_id=subscription_id, limit=limit)
