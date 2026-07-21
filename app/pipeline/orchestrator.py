"""Assessment pipeline orchestrator — cost → metrics → quality → recommendations."""

from __future__ import annotations

import json
import os
import uuid
import structlog
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db_locks import PIPELINE_ADVISORY_LOCK_ID, release_lock, try_acquire_lock
from app.models import PipelineRun
from app.pipeline.freshness import cost_data_fresh
from app.pipeline.store import iter_pipeline_enrichment_rows
from app.workers.cost_sync_worker import run_cost_sync_worker
from app.workers.data_quality_worker import run_data_quality_worker
from app.workers.inventory_metrics_worker import run_inventory_metrics_worker
from app.workers.recommendation_worker import run_recommendation_worker

log = structlog.get_logger(__name__)


def pipeline_enabled() -> bool:
    """Whether on-demand assessment pipeline runs (cost → metrics → quality → recommendations).

    Defaults to enabled — same as ``assessment_pipeline_primary()`` in analysis routing.
    Background scheduled pipelines are gated separately via ``scheduled_pipeline_enabled()``.
    """
    if os.getenv("ASSESSMENT_PIPELINE_ENABLED") is not None:
        return os.getenv("ASSESSMENT_PIPELINE_ENABLED", "true").lower() not in {"0", "false", "no"}
    return True


def _cost_data_fresh(db: Session, subscription_id: str) -> bool:
    return cost_data_fresh(db, subscription_id)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_pipeline_run(db: Session, subscription_id: str) -> PipelineRun:
    run = PipelineRun(
        id=str(uuid.uuid4()),
        subscription_id=subscription_id.lower(),
        status="queued",
        stage_results_json="{}",
        created_at=_now(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def run_pipeline(
    db: Session,
    subscription_id: str,
    *,
    pipeline_run: PipelineRun | None = None,
    skip_metrics: bool = False,
) -> dict[str, Any]:
    """Execute cost sync → metrics → data quality → recommendations."""
    sub = subscription_id.lower()
    if not pipeline_enabled():
        return {
            "status": "disabled",
            "reason": "assessment_pipeline_disabled",
            "hint": "Set ASSESSMENT_PIPELINE_ENABLED=true to enable the assessment pipeline.",
            "subscription_id": sub,
        }

    lock_held = False
    if not try_acquire_lock(db, PIPELINE_ADVISORY_LOCK_ID):
        return {"status": "skipped", "reason": "lock_held", "subscription_id": sub}
    lock_held = True

    run = pipeline_run or create_pipeline_run(db, sub)
    run.status = "running"
    run.started_at = _now()
    run.current_stage = "cost_sync"
    db.commit()

    stage_results: dict[str, Any] = {}

    try:
        stage_results["cost_sync"] = run_cost_sync_worker(db, sub)
        if stage_results["cost_sync"].get("status") == "fresh":
            stage_results["cost_check"] = {"status": "fresh"}
        elif stage_results["cost_sync"].get("status") == "ok":
            stage_results["cost_check"] = {"status": "fresh", "synced": True}
        elif _cost_data_fresh(db, sub):
            stage_results["cost_check"] = {"status": "fresh", "cost_sync_failed": True}
        else:
            stage_results["cost_check"] = {
                "status": "stale",
                "message": "Cost sync data is stale; quality scoring will cap missingCostData.",
                "cost_sync": stage_results["cost_sync"],
            }

        if not skip_metrics:
            run.current_stage = "inventory_metrics"
            db.commit()
            stage_results["inventory_metrics"] = run_inventory_metrics_worker(db, sub)
            stage_results["monitor_metrics"] = stage_results["inventory_metrics"]

        run.current_stage = "data_quality"
        db.commit()
        stage_results["data_quality"] = run_data_quality_worker(db, sub)

        run.current_stage = "unified_recommendations"
        db.commit()
        stage_results["unified_recommendations"] = run_recommendation_worker(db, sub)
        stage_results["recommendations"] = stage_results["unified_recommendations"]

        run.status = "completed"
        run.current_stage = "completed"
        run.completed_at = _now()
        run.stage_results_json = json.dumps(stage_results)
        db.commit()

        result = {
            "status": "ok",
            "subscription_id": sub,
            "pipeline_run_id": run.id,
            "stages": stage_results,
        }
        log.info("pipeline.completed", subscription_id=sub, pipeline_run_id=run.id)
        return result

    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)[:2000]
        run.completed_at = _now()
        run.stage_results_json = json.dumps(stage_results)
        db.commit()
        log.exception("pipeline.failed", subscription_id=sub, error=str(exc))
        raise
    finally:
        if lock_held:
            release_lock(db, PIPELINE_ADVISORY_LOCK_ID)


def pipeline_status_counts(db: Session, subscription_id: str) -> dict[str, int]:
    stage_aliases = {
        "metrics_ready": "metrics_collected",
        "recommended": "recommendations_ready",
    }

    sub = subscription_id.lower()
    counts: dict[str, int] = {}
    for row in iter_pipeline_enrichment_rows(db, sub):
        stage = row.pipeline_stage or "pending"
        key = stage_aliases.get(stage, stage)
        counts[key] = counts.get(key, 0) + 1
    return counts
