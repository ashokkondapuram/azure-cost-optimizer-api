"""Finding activity / audit trail."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import FindingActivity


def log_activity_entry(
    db: Session,
    *,
    finding_id: str,
    subscription_id: str,
    action: str = "note",
    from_status: str | None = None,
    to_status: str | None = None,
    user: dict | None = None,
    note: str | None = None,
) -> FindingActivity:
    entry = FindingActivity(
        id=str(uuid.uuid4()),
        finding_id=finding_id,
        subscription_id=(subscription_id or "").strip().lower(),
        action=(action or "note").strip() or "note",
        from_status=(from_status or "").lower() or None,
        to_status=(to_status or "").lower() or None,
        user_id=(user or {}).get("id"),
        user_name=(user or {}).get("display_name") or (user or {}).get("username"),
        note=note,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    return entry


def log_finding_status_change(
    db: Session,
    *,
    finding_id: str,
    subscription_id: str,
    from_status: str | None,
    to_status: str,
    user: dict | None = None,
    note: str | None = None,
) -> FindingActivity:
    return log_activity_entry(
        db,
        finding_id=finding_id,
        subscription_id=subscription_id,
        action="status_change",
        from_status=from_status,
        to_status=to_status or "open",
        user=user,
        note=note,
    )


def serialize_activity(row: FindingActivity) -> dict:
    return {
        "id": row.id,
        "finding_id": row.finding_id,
        "subscription_id": row.subscription_id,
        "action": row.action,
        "from_status": row.from_status,
        "to_status": row.to_status,
        "user_id": row.user_id,
        "user_name": row.user_name,
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def list_finding_activity(db: Session, *, finding_id: str, limit: int = 50) -> list[dict]:
    rows = (
        db.query(FindingActivity)
        .filter(FindingActivity.finding_id == finding_id)
        .order_by(FindingActivity.created_at.desc())
        .limit(limit)
        .all()
    )
    return [serialize_activity(r) for r in rows]
