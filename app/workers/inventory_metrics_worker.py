"""Inventory + Azure Monitor metrics collection using assessment JSON requirements."""

from __future__ import annotations

import os
import structlog
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.assessment.catalog import get_assessment_for_arm_type
from app.assessment.metrics_collector import build_assessment_metrics_plan
from app.assessment.normalizer import build_normalized_record
from app.assessment.spec import assessment_metadata, metrics_refresh_timespan
from it_services.sku_specs import load_sku_specs_for_canonical, sku_summary
from app.cost_db import resource_cost_map_from_db
from app.focus_mapping import normalize_arm_id
from app.monitor_metrics import (
    load_azure_monitor_metrics,
    sync_monitor_fetch_timeout_sec,
    sync_monitor_limit_per_type,
    sync_monitor_max_workers,
)
from app.monitor_metrics_retry import sync_monitor_max_retries
from app.models import ResourceSnapshot
from app.pipeline.store import (
    is_indexed_resource,
    persist_normalized_snapshot,
    resource_row_to_dict,
)
from app.resource_type_map import arm_provider_type

log = structlog.get_logger(__name__)


def inventory_metrics_worker_enabled() -> bool:
    return os.getenv("INVENTORY_METRICS_WORKER_ENABLED", "true").lower() not in {
        "0", "false", "no",
    }


def metrics_snapshot_interval_hours() -> float:
    return max(1.0, float(os.getenv("METRICS_SNAPSHOT_INTERVAL_HOURS", "6")))


def _pipeline_metrics_timespan(assessment_timespan: str | None) -> str | None:
    env_ts = os.getenv("ANALYSIS_MONITOR_METRICS_TIMESPAN") or os.getenv("ANALYSIS_VM_METRICS_TIMESPAN")
    return env_ts or assessment_timespan


def _pipeline_metrics_limit_per_type() -> int:
    raw = os.getenv(
        "ANALYSIS_MONITOR_METRICS_LIMIT_PER_TYPE",
        os.getenv("ANALYSIS_VM_METRICS_LIMIT", "0"),
    )
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def run_inventory_metrics_worker(
    db: Session,
    subscription_id: str,
    *,
    token: str | None = None,
    scoped_canonical_types: list[str] | set[str] | None = None,
    scoped_arm_ids: set[str] | None = None,
    sync_context: bool = False,
) -> dict[str, Any]:
    """Fetch Azure Monitor metrics defined in assessment JSON and persist snapshots."""
    sub = subscription_id.lower()
    stats: dict[str, Any] = {
        "subscription_id": sub,
        "resources_processed": 0,
        "metrics_loaded": 0,
        "metrics_empty": 0,
        "metrics_failed": 0,
        "skipped_not_indexed": 0,
        "assessment_types": 0,
        "sync_context": sync_context,
    }

    if not inventory_metrics_worker_enabled():
        stats["status"] = "disabled"
        return stats

    canonical_filter = (
        {t.strip().lower() for t in scoped_canonical_types}
        if scoped_canonical_types
        else None
    )
    plan = build_assessment_metrics_plan(
        db,
        sub,
        canonical_types=canonical_filter,
        arm_ids=scoped_arm_ids,
    )
    grouped = plan.get("grouped") or {}
    if not grouped:
        stats["status"] = "no_indexed_resources"
        return stats

    stats["assessment_types"] = len(plan.get("assessment_by_canonical") or {})
    stats["assessment_files"] = sorted({
        meta.get("assessment_file")
        for meta in (plan.get("assessment_by_canonical") or {}).values()
        if meta.get("assessment_file")
    })

    cost_map = resource_cost_map_from_db(db, sub)
    timespan = None
    for meta in (plan.get("assessment_by_canonical") or {}).values():
        arm_type = meta.get("resource_type") or ""
        full = get_assessment_for_arm_type(arm_type)
        if full:
            timespan = metrics_refresh_timespan(full) or timespan

    limit_per_type = _pipeline_metrics_limit_per_type()
    fetch_timeout_sec = None
    max_retries = None
    max_workers = None
    if sync_context:
        sync_limit = sync_monitor_limit_per_type()
        if sync_limit > 0:
            limit_per_type = sync_limit
        fetch_timeout_sec = sync_monitor_fetch_timeout_sec()
        max_retries = sync_monitor_max_retries()
        max_workers = sync_monitor_max_workers()
        stats["scoped_canonical_types"] = sorted(canonical_filter) if canonical_filter else None
        log.info(
            "inventory_metrics_worker.sync_context",
            subscription_id=sub,
            timeout_sec=fetch_timeout_sec,
            max_retries=max_retries,
            max_workers=max_workers,
            limit_per_type=limit_per_type,
            scoped_types=stats.get("scoped_canonical_types"),
        )

    _, resource_facts, monitor_stats = load_azure_monitor_metrics(
        grouped,
        cost_map,
        db=db,
        timespan=_pipeline_metrics_timespan(timespan),
        limit_per_type=limit_per_type,
        metric_names_by_canonical=plan.get("metric_names_by_canonical") or {},
        fetch_timeout_sec=fetch_timeout_sec,
        max_retries=max_retries,
        max_workers=max_workers,
    )
    stats["monitor_stats"] = monitor_stats
    stats["metrics_failed"] = int(monitor_stats.get("failed") or 0)
    stats["metrics_timed_out"] = int(monitor_stats.get("timed_out") or 0)

    required_by_canonical = plan.get("required_keys_by_canonical") or {}
    assessment_by_canonical = plan.get("assessment_by_canonical") or {}

    resources = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
            ResourceSnapshot.is_cost_export_only.is_(False),
        )
        .all()
    )
    allowed_arms = (
        {normalize_arm_id(rid).lower() for rid in scoped_arm_ids if normalize_arm_id(rid)}
        if scoped_arm_ids
        else None
    )
    for resource in resources:
        row_dict = resource_row_to_dict(resource)
        if not is_indexed_resource(row_dict["resource_id"]):
            stats["skipped_not_indexed"] += 1
            continue

        canonical = (row_dict.get("canonical_type") or "").strip().lower()
        if canonical_filter and canonical not in canonical_filter:
            continue
        rid_lower = row_dict["resource_id"].lower()
        if allowed_arms and rid_lower not in allowed_arms:
            continue
        try:
            facts = dict(resource_facts.get(rid_lower) or {})
            if facts:
                stats["metrics_loaded"] += 1
            else:
                stats["metrics_empty"] += 1
                facts = {"_partial": True}

            required_keys = required_by_canonical.get(canonical) or []
            arm_type = row_dict.get("resource_type") or arm_provider_type(row_dict["resource_id"]) or ""
            assessment = get_assessment_for_arm_type(arm_type)
            assessment_ref = assessment_by_canonical.get(canonical) or (
                assessment_metadata(assessment) if assessment else {}
            )

            record = build_normalized_record(
                row_dict,
                metrics=facts,
                required_metric_keys=required_keys or None,
                assessment=assessment,
            )
            if assessment_ref:
                record["assessment"] = assessment_ref
            sku_spec = load_sku_specs_for_canonical(canonical)
            if sku_spec:
                record["sku_specs"] = sku_spec
                record["sku_summary"] = sku_summary(sku_spec)

            from app.messaging.data_collector import get_collector

            collector = get_collector()
            if collector is not None:
                records = collector.sections.setdefault("metrics_records", [])
                records.append(
                    {
                        "resource_id": row_dict.get("resource_id"),
                        "row_dict": row_dict,
                        "facts": facts,
                        "normalized_record": record,
                    }
                )
                stats["resources_processed"] += 1
                continue

            persist_normalized_snapshot(
                db,
                subscription_id=sub,
                row_dict=row_dict,
                metrics=facts,
                pipeline_stage="metrics_ready",
                normalized_record=record,
            )
            try:
                from app.data_store.resource_enrichment import upsert_metrics

                upsert_metrics(db, resource, facts)
            except Exception as exc:
                log.warning(
                    "enrichment_metrics_upsert_failed",
                    resource_id=row_dict.get("resource_id"),
                    error=str(exc)[:200],
                )
            stats["resources_processed"] += 1
        except Exception as exc:
            stats["metrics_failed"] = int(stats.get("metrics_failed") or 0) + 1
            log.warning(
                "inventory_metrics_worker.persist_failed",
                subscription_id=sub,
                resource_id=row_dict.get("resource_id"),
                canonical=canonical,
                error=str(exc)[:200],
            )

    db.commit()
    if stats["metrics_failed"] or stats.get("metrics_timed_out"):
        stats["status"] = "partial"
        log.warning(
            "inventory_metrics_worker.partial",
            subscription_id=sub,
            metrics_failed=stats["metrics_failed"],
            metrics_timed_out=stats.get("metrics_timed_out"),
            metrics_loaded=stats["metrics_loaded"],
        )
    else:
        stats["status"] = "ok"
    stats["completed_at"] = datetime.now(timezone.utc).isoformat()
    log.info("inventory_metrics_worker.done", **{k: v for k, v in stats.items() if k != "monitor_stats"})
    return stats
