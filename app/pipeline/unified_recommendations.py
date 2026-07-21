"""Unified recommendation engine — legacy sub-engines with assessment JSON rules."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

import structlog
from sqlalchemy.orm import Session

from app.models import OptimizationRun
from app.pipeline.store import iter_pipeline_enrichment_rows
from app.workers.legacy_engine_worker import run_legacy_engine_worker

log = structlog.get_logger(__name__)

UNIFIED_PROFILE = "unified"
UNIFIED_ENGINE_VERSION = "extended+assessment_json"
UNIFIED_DATA_SOURCE = "sub_engines"


def run_unified_recommendations(db: Session, subscription_id: str) -> dict[str, Any]:
    """Run sub-engines (assessment JSON rules + Python analyzers) and persist one run."""
    sub = subscription_id.lower()
    stats: dict[str, Any] = {
        "subscription_id": sub,
        "findings": 0,
    }

    engine_stats = run_legacy_engine_worker(db, sub)
    stats.update({k: v for k, v in engine_stats.items() if k != "finding_rows"})
    stats["findings"] = engine_stats.get("findings", 0)

    _mark_snapshots_recommended(db, sub)
    db.commit()

    stats["status"] = stats.get("status", "ok")
    stats["completed_at"] = datetime.now(timezone.utc).isoformat()
    log.info("unified_recommendations.done", subscription_id=sub, findings=stats["findings"])
    return stats


def _mark_snapshots_recommended(db: Session, subscription_id: str) -> int:
    sub = subscription_id.lower()
    now = datetime.now(timezone.utc)
    updated = 0
    for row in iter_pipeline_enrichment_rows(db, sub):
        if (row.pipeline_stage or "") == "quality_scored":
            row.pipeline_stage = "recommended"
            row.updated_at = now
            updated += 1
    return updated


def run_analysis_via_unified_pipeline(
    db: Session,
    *,
    subscription_id: str,
    profile: str = "default",
    engine_version: str = "extended",
    progress_callback: Callable[[int, str | None], None] | None = None,
) -> dict[str, Any]:
    """Run the full pipeline and return a run_db_analysis-compatible payload."""
    from app.pipeline.orchestrator import run_pipeline

    sub = subscription_id.lower()
    if progress_callback:
        progress_callback(10, "unified_pipeline")

    pipeline_result = run_pipeline(db, sub)
    status = pipeline_result.get("status")

    if progress_callback:
        progress_callback(90, "unified_pipeline")

    if status == "disabled":
        reason = pipeline_result.get("reason") or "assessment_pipeline_disabled"
        hint = pipeline_result.get("hint") or "Set ASSESSMENT_PIPELINE_ENABLED=true."
        raise ValueError(
            f"Unified analysis pipeline is disabled ({reason}). {hint}"
        )

    if status != "ok":
        reason = pipeline_result.get("reason") or status
        raise ValueError(
            f"Unified analysis pipeline did not complete successfully ({status}: {reason})."
        )

    rec = (pipeline_result.get("stages") or {}).get("recommendations") or {}
    run_id = rec.get("run_id")
    if not run_id:
        result = _empty_analysis_from_recommendations(
            db,
            subscription_id=sub,
            profile=profile,
            engine_version=engine_version,
            rec=rec,
        )
        if progress_callback:
            progress_callback(100, None)
        return result

    run = db.query(OptimizationRun).filter(OptimizationRun.id == run_id).first()
    if not run:
        result = _empty_analysis_from_recommendations(
            db,
            subscription_id=sub,
            profile=profile,
            engine_version=engine_version,
            rec=rec,
        )
        if progress_callback:
            progress_callback(100, None)
        return result

    findings = _load_findings_json(run.findings_json)
    summary = {
        "total_findings": run.total_findings or len(findings),
        "total_estimated_monthly_savings_usd": float(run.total_savings_usd or 0),
        "by_severity": {
            "CRITICAL": int(run.critical_count or 0),
            "HIGH": int(run.high_count or 0),
            "MEDIUM": int(run.medium_count or 0),
            "LOW": int(run.low_count or 0),
        },
    }

    if progress_callback:
        progress_callback(100, None)

    return {
        "findings": findings,
        "summary": summary,
        "data_source": UNIFIED_DATA_SOURCE,
        "analysis_trigger": "unified_pipeline",
        "engine_version": engine_version,
        "profile": profile,
        "run_id": run_id,
        "pipeline_run_id": pipeline_result.get("pipeline_run_id"),
    }


def _load_findings_json(raw: str | None) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return [row for row in parsed if isinstance(row, dict)]


def _empty_analysis_from_recommendations(
    db: Session,
    *,
    subscription_id: str,
    profile: str,
    engine_version: str,
    rec: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "summary": {
            "total_findings": int(rec.get("findings") or 0),
            "total_estimated_monthly_savings_usd": 0.0,
            "by_severity": {},
        },
        "findings": [],
        "data_source": UNIFIED_DATA_SOURCE,
        "analysis_trigger": "unified_pipeline",
    }
    from app.analysis_persist import persist_optimization_run

    result["run_id"] = persist_optimization_run(
        db,
        subscription_id=subscription_id,
        profile=profile,
        engine_version=engine_version,
        result=result,
        data_source=UNIFIED_DATA_SOURCE,
    )
    return result
