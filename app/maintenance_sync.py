"""Persist planned maintenance from Azure and serve it from the database."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.azure_maintenance import AzureMaintenanceClient, _is_upcoming, _parse_dt
from app.http_client import arm_patient_sync
from app.models import MaintenanceSyncRun, PlannedMaintenanceItem

log = structlog.get_logger(__name__)

_ROW_FIELDS = (
    "id",
    "source",
    "resource_type",
    "resource_name",
    "resource_id",
    "resource_group",
    "location",
    "title",
    "status",
    "window_start",
    "window_end",
    "detail",
)

_sync_locks: dict[str, threading.Lock] = {}
_sync_locks_guard = threading.Lock()
_sync_in_progress: set[str] = set()
_sync_in_progress_guard = threading.Lock()


def _subscription_sync_lock(subscription_id: str) -> threading.Lock:
    sub = subscription_id.strip().lower()
    with _sync_locks_guard:
        if sub not in _sync_locks:
            _sync_locks[sub] = threading.Lock()
        return _sync_locks[sub]


def is_maintenance_sync_running(subscription_id: str) -> bool:
    sub = (subscription_id or "").strip().lower()
    with _sync_in_progress_guard:
        return sub in _sync_in_progress


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _item_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Extra fields not stored in dedicated columns."""
    payload = {k: v for k, v in row.items() if k not in _ROW_FIELDS and v is not None}
    return payload


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one row per external id (last occurrence wins)."""
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        external_id = str(item.get("id") or "").strip()
        if not external_id:
            external_id = str(uuid.uuid4())
        deduped[external_id] = item
    return list(deduped.values())


def _row_to_item_dict(row: PlannedMaintenanceItem) -> dict[str, Any]:
    item = {
        "id": row.external_id,
        "source": row.source,
        "resource_type": row.resource_type,
        "resource_name": row.resource_name,
        "resource_id": row.resource_id,
        "resource_group": row.resource_group,
        "location": row.location,
        "title": row.title,
        "status": row.status,
        "window_start": row.window_start,
        "window_end": row.window_end,
        "detail": row.detail,
    }
    try:
        extras = json.loads(row.payload_json or "{}")
        if isinstance(extras, dict):
            item.update(extras)
    except (TypeError, json.JSONDecodeError):
        pass
    return item


def filter_upcoming_items(items: list[dict[str, Any]], *, upcoming_only: bool) -> list[dict[str, Any]]:
    """Keep only future or in-progress maintenance windows (exclude historical activity log)."""
    if not upcoming_only:
        return items

    filtered: list[dict[str, Any]] = []
    for row in items:
        if row.get("origin") == "activity_log" or row.get("source") == "activity_log":
            continue
        if row.get("pending_model_update") or row.get("pending_model_updates"):
            filtered.append(row)
            continue
        if row.get("window_start") or row.get("window_end"):
            if _is_upcoming(row.get("window_start"), row.get("window_end")):
                filtered.append(row)
    return filtered


def _filter_upcoming(items: list[dict[str, Any]], upcoming_only: bool) -> list[dict[str, Any]]:
    return filter_upcoming_items(items, upcoming_only=upcoming_only)


def _build_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    by_source: dict[str, int] = {}
    for row in items:
        source = row.get("source") or "other"
        by_source[source] = by_source.get(source, 0) + 1
    return {
        "health_events": by_source.get("health_event", 0),
        "vms": by_source.get("vm", 0),
        "vmss": by_source.get("vmss", 0),
        "vmss_instances": by_source.get("vmss_instance", 0),
    }


def get_last_sync_run(db: Session, subscription_id: str) -> MaintenanceSyncRun | None:
    sub = subscription_id.strip().lower()
    return (
        db.query(MaintenanceSyncRun)
        .filter(MaintenanceSyncRun.subscription_id == sub)
        .order_by(desc(MaintenanceSyncRun.started_at))
        .first()
    )


def load_planned_maintenance_from_db(
    db: Session,
    subscription_id: str,
    *,
    upcoming_only: bool = True,
) -> dict[str, Any]:
    """Return cached planned maintenance for a subscription."""
    sub = subscription_id.strip().lower()
    rows = (
        db.query(PlannedMaintenanceItem)
        .filter(PlannedMaintenanceItem.subscription_id == sub)
        .all()
    )
    items = [_row_to_item_dict(row) for row in rows]
    items = _filter_upcoming(items, upcoming_only)
    items.sort(key=lambda row: row.get("window_start") or "9999-12-31T23:59:59Z")

    last_run = get_last_sync_run(db, sub)
    synced_at = None
    if rows:
        synced_at = max((row.synced_at for row in rows if row.synced_at), default=None)
    if last_run and last_run.finished_at:
        synced_at = last_run.finished_at

    return {
        "subscription_id": sub,
        "count": len(items),
        "upcoming_only": upcoming_only,
        "data_source": "database",
        "synced_at": synced_at.isoformat() if synced_at else None,
        "last_sync_status": last_run.status if last_run else None,
        "sync_in_progress": is_maintenance_sync_running(sub),
        "summary": _build_summary(items),
        "items": items,
    }


def sync_planned_maintenance(
    db: Session,
    subscription_id: str,
    *,
    upcoming_only: bool = True,
) -> dict[str, Any]:
    """Fetch planned maintenance from Azure and replace cached rows."""
    sub = subscription_id.strip().lower()
    lock = _subscription_sync_lock(sub)
    acquired = lock.acquire(blocking=False)
    if not acquired:
        log.info("maintenance_sync.skipped_in_progress", subscription_id=sub)
        result = load_planned_maintenance_from_db(db, sub, upcoming_only=upcoming_only)
        result["sync_skipped"] = True
        result["message"] = "Sync already in progress. Serving cached data."
        return result

    with _sync_in_progress_guard:
        _sync_in_progress.add(sub)
    run_id = str(uuid.uuid4())
    started = _now()
    run = MaintenanceSyncRun(
        id=run_id,
        subscription_id=sub,
        started_at=started,
        status="running",
    )
    db.add(run)
    db.commit()

    try:
        client = AzureMaintenanceClient(db=db)
        with arm_patient_sync():
            payload = client.list_planned_maintenance(sub, upcoming_only=True)
        items = _dedupe_items(payload.get("items") or [])
        synced_at = _now()

        db.query(PlannedMaintenanceItem).filter(
            PlannedMaintenanceItem.subscription_id == sub
        ).delete(synchronize_session=False)

        for item in items:
            external_id = str(item.get("id") or uuid.uuid4())
            db.add(
                PlannedMaintenanceItem(
                    id=str(uuid.uuid4()),
                    subscription_id=sub,
                    external_id=external_id,
                    source=item.get("source") or "other",
                    resource_type=item.get("resource_type"),
                    resource_name=item.get("resource_name"),
                    resource_id=item.get("resource_id"),
                    resource_group=item.get("resource_group"),
                    location=item.get("location"),
                    title=item.get("title"),
                    status=item.get("status"),
                    window_start=item.get("window_start"),
                    window_end=item.get("window_end"),
                    detail=item.get("detail"),
                    payload_json=json.dumps(_item_payload(item)),
                    sync_run_id=run_id,
                    synced_at=synced_at,
                )
            )

        run.status = "success"
        run.finished_at = synced_at
        run.items_count = len(items)
        db.commit()

        log.info(
            "maintenance_sync.complete",
            subscription_id=sub,
            items=len(items),
            run_id=run_id,
        )
        result = load_planned_maintenance_from_db(db, sub, upcoming_only=upcoming_only)
        result["data_source"] = "azure"
        result["synced_at"] = synced_at.isoformat()
        result["last_sync_status"] = "success"
        return result
    except Exception as exc:
        db.rollback()
        failed_run = db.query(MaintenanceSyncRun).filter(MaintenanceSyncRun.id == run_id).first()
        if failed_run:
            failed_run.status = "failed"
            failed_run.finished_at = _now()
            failed_run.error_message = str(exc)[:2000]
        db.commit()
        log.exception("maintenance_sync.failed", subscription_id=sub, error=str(exc)[:300])
        raise
    finally:
        with _sync_in_progress_guard:
            _sync_in_progress.discard(sub)
        lock.release()
