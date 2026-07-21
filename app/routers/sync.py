"""Unified sync pipeline endpoints."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.auth import arm_bearer_token
from app.database import get_db
from app.sync_orchestrator import (
    cancel_full_sync_pipeline,
    get_pipeline_status,
    request_full_sync,
    reset_full_sync_pipeline,
)
from app.sync_progress import build_progress_response, get_subscription_progress
from app.sync_scope import normalize_sync_types
from app.user_auth import require_admin_user
from app.validators import ensure_subscription_known
import structlog

log = structlog.get_logger()
router = APIRouter(tags=["Sync"])


def _scoped_subscription(db: Session, subscription_id: str) -> str:
    return ensure_subscription_known(db, subscription_id)


@router.post(
    "/sync/full",
    summary="Run full sync pipeline (inventory → cost → metrics → analysis)",
    status_code=202,
    responses={
        200: {"description": "Pipeline completed (wait=true only)"},
        202: {"description": "Pipeline accepted and running in the background"},
    },
)
def trigger_full_sync(
    request: Request,
    subscription_id: str = Query(...),
    types: Optional[str] = Query(
        None,
        description="Comma-separated canonical types for scoped inventory sync.",
    ),
    include_costs: bool = Query(True, description="Run cost sync stage after inventory."),
    components: Optional[str] = Query(
        None,
        description="Comma-separated optimization components for scoped analysis.",
    ),
    wait: bool = Query(
        False,
        description="Block until the full pipeline completes. May time out behind gateways.",
    ),
    force: bool = Query(
        False,
        description="Cancel any active pipeline and start a new one.",
    ),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    sub = subscription_id.strip().lower()

    type_list = None
    scope_resource_types = None
    if types:
        type_list = [t.strip() for t in types.split(",") if t.strip()]
        types_set = normalize_sync_types(type_list)
        if types_set:
            scope_resource_types = sorted(types_set)

    scope_components = None
    if components:
        scope_components = [c.strip() for c in components.split(",") if c.strip()] or None

    if wait:
        token = arm_bearer_token(db)
        sub = _scoped_subscription(db, sub)
        from app.batch_analyzer import create_analysis_job, execute_batch_job
        from app.cost_explorer_sync import sync_cost_explorer
        from app.db_sync import sync_all, sync_scoped
        from app.sync_orchestrator import assert_inventory_persisted
        from app.workers.inventory_metrics_worker import run_inventory_metrics_worker

        try:
            log.info("full_sync.wait_start", subscription_id=sub)
            if scope_resource_types:
                inventory = sync_scoped(sub, db, token, scope_resource_types, include_costs=False)
            else:
                inventory = sync_all(sub, db, token)
            assert_inventory_persisted(inventory, scoped=bool(scope_resource_types))
            cost = sync_cost_explorer(sub, db, token) if include_costs else {"status": "skipped"}
            metrics = run_inventory_metrics_worker(db, sub, token=token)
            analysis_types = scope_resource_types
            job = create_analysis_job(
                db,
                subscription_id=sub,
                scope_components=scope_components,
                scope_resource_types=analysis_types,
                skip_monitor_fetch=True,
            )
            execute_batch_job(job.id)
            payload = {
                "status": "ok",
                "async": False,
                "subscription_id": sub,
                "stages": {
                    "inventory": inventory,
                    "cost": cost,
                    "metrics": metrics,
                    "analysis": {"job_id": job.id, "status": job.status},
                },
            }
            log.info("full_sync.wait_done", subscription_id=sub, job_id=job.id)
            return JSONResponse(status_code=200, content=payload)
        except Exception as exc:
            log.exception("full_sync.wait_failed", subscription_id=sub)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    enqueued, payload = request_full_sync(
        sub,
        token=None,
        type_list=type_list,
        include_costs=include_costs,
        scope_components=scope_components,
        scope_resource_types=scope_resource_types,
        reason="manual_full_sync",
        force=force,
    )
    log.info(
        "full_sync.enqueued",
        subscription_id=sub,
        enqueued=enqueued,
        scoped_types=scope_resource_types,
        include_costs=include_costs,
    )
    return JSONResponse(status_code=202, content=payload)


@router.get("/sync/pipeline", summary="Unified sync pipeline status")
def full_sync_pipeline_status(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    sub = _scoped_subscription(db, subscription_id.strip().lower())
    pipeline = get_pipeline_status(sub)
    progress = get_subscription_progress(sub, resume=True)
    return {
        "subscription_id": sub,
        "pending": bool(pipeline and pipeline.get("pending")),
        "pipeline": pipeline,
        "progress": progress,
    }


def _parse_subscription_ids(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    parts = [part.strip().lower() for part in raw.split(",") if part.strip()]
    return list(dict.fromkeys(parts)) or None


@router.get(
    "/sync/progress",
    summary="Active sync pipeline progress for dashboard (multi-subscription)",
)
def sync_progress(
    request: Request,
    subscription_id: Optional[str] = Query(
        None,
        description="Comma-separated subscription IDs. Omit to return all active pipelines.",
    ),
    active_only: bool = Query(True, description="Return only queued/running pipelines."),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    subs = _parse_subscription_ids(subscription_id)
    if subs:
        for sub in subs:
            ensure_subscription_known(db, sub)
    return build_progress_response(subs, active_only=active_only, resume=True)


@router.get(
    "/sync/progress/stream",
    summary="SSE stream for real-time sync pipeline progress",
)
async def sync_progress_stream(
    request: Request,
    subscription_id: Optional[str] = Query(
        None,
        description="Optional subscription filter. Omit to stream all active pipelines.",
    ),
    db: Session = Depends(get_db),
):
    """Real-time sync progress via Server-Sent Events.

    The dashboard may also poll ``GET /sync/progress`` every 2–3 seconds when SSE is unavailable.
    """
    from app.sync_pipeline_events import subscribe_sync_progress_events

    require_admin_user(request)
    subs = _parse_subscription_ids(subscription_id)
    if subs:
        for sub in subs:
            ensure_subscription_known(db, sub)

    async def event_generator():
        snapshot = build_progress_response(subs, active_only=True, resume=False)
        yield f"data: {json.dumps({'type': 'snapshot', **snapshot}, default=str)}\n\n"

        if subs and len(subs) == 1:
            async for chunk in subscribe_sync_progress_events(subs[0]):
                if await request.is_disconnected():
                    break
                yield chunk
            return

        async for chunk in subscribe_sync_progress_events(all_subscriptions=True):
            if await request.is_disconnected():
                break
            if subs:
                # Filter broadcast events to requested subscriptions when multiple IDs are passed.
                if chunk.startswith("data: "):
                    try:
                        payload = json.loads(chunk[6:].strip())
                        progress = payload.get("progress") or {}
                        if progress.get("subscription_id") not in subs:
                            continue
                    except (TypeError, ValueError, json.JSONDecodeError):
                        pass
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sync/pipeline/cancel", summary="Cancel the active sync pipeline")
def cancel_sync_pipeline(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    sub = _scoped_subscription(db, subscription_id.strip().lower())
    payload = cancel_full_sync_pipeline(sub)
    log.info("full_sync.cancelled", subscription_id=sub, status=payload.get("status"))
    return payload


@router.post("/sync/reset", summary="Reset stuck sync pipeline state (admin)")
def reset_sync_pipeline(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    sub = _scoped_subscription(db, subscription_id.strip().lower())
    payload = reset_full_sync_pipeline(sub)
    log.info("full_sync.reset", subscription_id=sub, status=payload.get("status"))
    return payload
