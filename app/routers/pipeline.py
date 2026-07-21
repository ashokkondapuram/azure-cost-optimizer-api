"""Assessment pipeline status and resource assessment API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.assessment.catalog import get_assessment_for_arm_type, load_assessment_index
from app.database import get_db
from app.focus_mapping import normalize_arm_id
from app.models import PipelineRun, ResourceAssessmentResult
from app.pipeline.orchestrator import pipeline_status_counts, run_pipeline
from app.pipeline.store import get_pipeline_row_by_arm, load_snapshot_dict
from app.resource_type_map import arm_provider_type
from app.scheduler_utils import list_subscription_ids
from app.optimizer.analysis_routing import analysis_routing_status

router = APIRouter(prefix="/pipeline", tags=["Assessment Pipeline"])


@router.get("/services")
def list_it_services() -> dict[str, Any]:
    """List all IT service entities and their working modules."""
    from it_services.registry import list_service_entities

    entities = list_service_entities()
    return {
        "count": len(entities),
        "services": [
            {
                "service_id": e["service_id"],
                "package": e["package"],
                "canonical_type": e["canonical_type"],
                "arm_type": e["arm_type"],
                "has_engine": e["has_engine"],
                "sub_engine_class": e["sub_engine_class"],
                "assessment_file": e["assessment_file"],
            }
            for e in entities
        ],
    }


@router.get("/routing")
def pipeline_routing_status() -> dict[str, Any]:
    """Show recommendation routing — assessment JSON rules run inside sub-engines."""
    return analysis_routing_status()


@router.get("/status")
def pipeline_status(
    subscription_id: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Per-subscription pipeline stage counts and latest pipeline run."""
    subs = [subscription_id.lower()] if subscription_id else list_subscription_ids(db)
    index = load_assessment_index()
    out: dict[str, Any] = {
        "indexed_assessment_files": index.get("totalAssessmentFiles"),
        "subscriptions": {},
    }
    for sub in subs:
        latest_run = (
            db.query(PipelineRun)
            .filter(PipelineRun.subscription_id == sub)
            .order_by(PipelineRun.created_at.desc())
            .first()
        )
        out["subscriptions"][sub] = {
            "stage_counts": pipeline_status_counts(db, sub),
            "latest_run": _serialize_run(latest_run) if latest_run else None,
        }
    return out


@router.post("/run/{subscription_id}")
def trigger_pipeline(
    subscription_id: str,
    skip_metrics: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run the full assessment pipeline for one subscription."""
    sub = subscription_id.strip().lower()
    if sub not in list_subscription_ids(db):
        raise HTTPException(status_code=404, detail="Subscription not found")
    return run_pipeline(db, sub, skip_metrics=skip_metrics)


@router.get("/resources/{resource_id}/assessment")
def resource_assessment(
    resource_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return data quality score and snapshot stage for a resource."""
    rid = normalize_arm_id(resource_id)
    snap = get_pipeline_row_by_arm(db, rid)
    if not snap:
        raise HTTPException(status_code=404, detail="No enrichment snapshot for resource")

    result = (
        db.query(ResourceAssessmentResult)
        .filter(ResourceAssessmentResult.resource_id == rid)
        .first()
    )
    arm_type = arm_provider_type(rid) or ""
    assessment = get_assessment_for_arm_type(arm_type or "")

    return {
        "resource_id": rid,
        "resource_type": arm_type,
        "pipeline_stage": snap.pipeline_stage,
        "metrics_fresh_at": snap.metrics_at.isoformat() if snap.metrics_at else None,
        "cost_fresh_at": snap.cost_at.isoformat() if snap.cost_at else None,
        "assessment_file": assessment.get("_file") if assessment else None,
        "score": result.score if result else None,
        "classification": result.classification if result else None,
        "data_quality": _parse_json(result.data_quality_json) if result else None,
    }


def _serialize_run(run: PipelineRun | None) -> dict[str, Any] | None:
    if not run:
        return None
    return {
        "id": run.id,
        "status": run.status,
        "current_stage": run.current_stage,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _parse_json(text: str | None) -> Any:
    import json
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}
