"""Legacy sub-engine pass — runs it_services/*/engine with assessment JSON rules."""

from __future__ import annotations

import os
import structlog
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.analysis.orchestrator import (
    load_budgets_from_db,
    load_cost_by_resource_from_db,
    load_inventory_from_db,
    run_engine_on_buckets,
)
from app.analysis_persist import persist_optimization_run
from app.finding_dedupe import merge_unified_findings
from app.recommendation_output import filter_valid_recommendations
from app.metrics_loader import load_cached_resource_facts
from app.optimizer.analysis_routing import integrated_sub_engines_enabled
from app.pipeline.store import load_pipeline_resource_facts

log = structlog.get_logger(__name__)


def legacy_engine_worker_enabled() -> bool:
    return integrated_sub_engines_enabled()


def run_legacy_engine_worker(db: Session, subscription_id: str) -> dict[str, Any]:
    """Run per-resource and platform sub-engines using pipeline metrics snapshots."""
    sub = subscription_id.lower()
    stats: dict[str, Any] = {
        "subscription_id": sub,
        "findings": 0,
        "status": "skipped",
    }

    if not legacy_engine_worker_enabled():
        stats["reason"] = "disabled"
        return stats

    buckets, _, aks_node_pools = load_inventory_from_db(db, sub, parallel=True)
    cost_by_resource = load_cost_by_resource_from_db(db, sub)
    budgets = load_budgets_from_db(db, sub)

    resource_facts = load_pipeline_resource_facts(db, sub)
    for rid, facts in load_cached_resource_facts(db, sub).items():
        merged = dict(resource_facts.get(rid) or {})
        merged.update(facts)
        resource_facts[rid] = merged

    profile = os.getenv("PIPELINE_LEGACY_PROFILE", "default")
    engine_version = os.getenv("ENGINE_VERSION", "extended").lower()

    result = run_engine_on_buckets(
        db,
        subscription_id=sub,
        buckets=buckets,
        aks_node_pools=aks_node_pools,
        cost_by_resource=cost_by_resource,
        budgets=budgets,
        profile=profile,
        engine_version=engine_version,
        load_metrics=False,
        resource_facts=resource_facts,
        include_ai=False,
    )

    findings: list[dict[str, Any]] = []
    for row in result.get("findings") or []:
        if not isinstance(row, dict):
            continue
        finding = dict(row)
        finding.setdefault("subscription_id", sub)
        finding.setdefault("data_source", "sub_engines")
        findings.append(finding)

    findings = merge_unified_findings(findings)
    findings = filter_valid_recommendations(findings)
    stats["findings"] = len(findings)
    stats["status"] = "ok"
    stats["summary"] = result.get("summary") or {}
    stats["metrics_context"] = result.get("metrics_context") or {}
    stats["completed_at"] = datetime.now(timezone.utc).isoformat()

    if findings:
        persist_result = {
            "findings": findings,
            "summary": {
                **(stats["summary"] or {}),
                "total_findings": len(findings),
                "total_estimated_monthly_savings_usd": sum(
                    float(f.get("estimated_savings_usd") or 0) for f in findings
                ),
            },
        }
        run_id = persist_optimization_run(
            db,
            subscription_id=sub,
            profile=os.getenv("PIPELINE_LEGACY_PROFILE", "unified"),
            engine_version="extended+assessment_json",
            result=persist_result,
            data_source="sub_engines",
        )
        stats["run_id"] = run_id

    log.info("legacy_engine_worker.done", subscription_id=sub, findings=len(findings))
    return {**stats, "finding_rows": findings}
