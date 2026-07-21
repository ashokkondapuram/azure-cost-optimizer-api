"""Persist sync data from Kafka data topics into PostgreSQL (idempotent upserts)."""

from __future__ import annotations

from typing import Any

import structlog

from app.messaging.data_ack import already_persisted, signal_persisted
from app.messaging.job_envelope import JobEnvelope, JobType

log = structlog.get_logger(__name__)

_DATA_STAGE_BY_JOB: dict[JobType, str] = {
    JobType.DATA_INVENTORY_SYNCED: "inventory",
    JobType.DATA_COST_SYNCED: "cost",
    JobType.DATA_METRICS_SYNCED: "metrics",
    JobType.DATA_ANALYSIS_COMPLETED: "analysis",
}


def _data_payload(envelope: JobEnvelope) -> dict[str, Any]:
    payload = envelope.payload or {}
    data = payload.get("data")
    return dict(data) if isinstance(data, dict) else {}


def _run_params(envelope: JobEnvelope) -> dict[str, Any]:
    payload = envelope.payload or {}
    run_params = payload.get("run_params")
    return dict(run_params) if isinstance(run_params, dict) else {}


def persist_data_envelope(envelope: JobEnvelope) -> None:
    """Route a data-topic envelope to the correct persistence handler."""
    stage = _DATA_STAGE_BY_JOB.get(envelope.job_type)
    if stage is None:
        log.warning(
            "data_persist.unexpected_job_type",
            job_type=envelope.job_type.value,
            pipeline_id=envelope.pipeline_id,
        )
        return

    pipeline_id = envelope.pipeline_id
    if already_persisted(pipeline_id, stage):
        log.info(
            "data_persist.skip_duplicate",
            stage=stage,
            pipeline_id=pipeline_id,
        )
        return

    handlers = {
        "inventory": _persist_inventory_data,
        "cost": _persist_cost_data,
        "metrics": _persist_metrics_data,
        "analysis": _persist_analysis_data,
    }
    handler = handlers[stage]
    handler(envelope, _data_payload(envelope), _run_params(envelope))
    signal_persisted(pipeline_id, stage)
    log.info(
        "data_persist.done",
        stage=stage,
        pipeline_id=pipeline_id,
        subscription_id=envelope.subscription_id,
    )


def _persist_inventory_data(
    envelope: JobEnvelope,
    data: dict[str, Any],
    run_params: dict[str, Any],
) -> None:
    from app.auth import arm_auth_context
    from app.bulk_resource_upsert import bulk_upsert_snapshots
    from app.database import SessionLocal
    from app.db_sync import (
        _dedupe_resource_snapshots,
        ensure_subscription_cache_row,
        sync_subscription_catalog,
    )
    from app.resource_pricing import dedupe_resource_pricing_profiles, upsert_resource_pricing_profile

    sub = envelope.subscription_id
    sections = data.get("sections") or {}
    batches = sections.get("inventory_batches") or []

    db = SessionLocal()
    try:
        bearer = (run_params.get("token") or "").strip()
        with arm_auth_context(db=db, token=bearer or None):
            try:
                sync_subscription_catalog(db)
            except Exception as exc:
                log.warning("data_persist.catalog_sync_failed", error=str(exc)[:200])
                ensure_subscription_cache_row(db, sub)

            for batch in batches:
                canonical_type = str(batch.get("canonical_type") or "")
                mappings = batch.get("mappings") or []
                if not canonical_type or not mappings:
                    continue
                bulk_upsert_snapshots(db, sub, mappings)
                for mapping in mappings:
                    raw_sku_json = mapping.get("sku_json")
                    if isinstance(raw_sku_json, str):
                        import json

                        sku_json_dict = json.loads(raw_sku_json) if raw_sku_json else {}
                    else:
                        sku_json_dict = raw_sku_json if raw_sku_json is not None else {}
                    upsert_resource_pricing_profile(
                        db,
                        subscription_id=sub,
                        resource_id=mapping["resource_id"],
                        resource_name=mapping["resource_name"],
                        canonical_type=canonical_type,
                        sku_label=mapping.get("sku"),
                        sku_json=sku_json_dict,
                        cost_mtd=float(mapping.get("monthly_cost_usd") or 0.0),
                    )

            post_sync = sections.get("post_sync") or {}
            if post_sync.get("dedupe_snapshots"):
                removed = _dedupe_resource_snapshots(db, sub)
                if removed:
                    log.info("data_persist.deduped_snapshots", removed=removed)
            if post_sync.get("dedupe_pricing"):
                removed_pricing = dedupe_resource_pricing_profiles(db, sub)
                if removed_pricing:
                    log.info("data_persist.deduped_pricing", removed=removed_pricing)

            advisor = sections.get("advisor")
            if isinstance(advisor, dict) and advisor.get("enabled"):
                from app.advisor_sync import sync_azure_advisor_recommendations

                if bearer:
                    sync_azure_advisor_recommendations(sub, db, bearer)

            ensure_subscription_cache_row(db, sub)
            db.commit()
    finally:
        db.close()


def _persist_cost_data(
    envelope: JobEnvelope,
    data: dict[str, Any],
    run_params: dict[str, Any],
) -> None:
    from app.auth import arm_auth_context
    from app.billed_resources import reconcile_billed_azure_status
    from app.cost_explorer_sync import _persist_mtd_by_resource_type_agg, _replace_daily_subscription_costs
    from app.database import SessionLocal
    from app.db_sync import (
        _compute_service_changes,
        _previous_service_totals,
        _record_cost_sync_run,
        _replace_mtd_by_resource_agg,
        _replace_mtd_by_service_agg,
        sync_resource_costs_from_cost_table,
    )

    sub = envelope.subscription_id
    sections = data.get("sections") or {}
    meta = sections.get("cost_meta") or {}
    month = str(meta.get("month") or "")

    db = SessionLocal()
    try:
        bearer = (run_params.get("token") or "").strip()
        with arm_auth_context(db=db, token=bearer or None):
            if sections.get("cost_by_service"):
                _replace_mtd_by_service_agg(db, sub, month, sections["cost_by_service"])
            if sections.get("cost_by_resource_type"):
                _persist_mtd_by_resource_type_agg(db, sub, month, sections["cost_by_resource_type"])
            if sections.get("daily_export_rows"):
                _replace_daily_subscription_costs(
                    db,
                    sub,
                    sections["daily_export_rows"],
                    mtd_start=str(meta.get("daily_history_start") or meta.get("mtd_start") or ""),
                    mtd_end=str(meta.get("mtd_end") or ""),
                )
            if sections.get("cost_by_resource"):
                _replace_mtd_by_resource_agg(db, sub, month, sections["cost_by_resource"])
                sync_resource_costs_from_cost_table(sub, db, month=month)
                reconcile_billed_azure_status(db, sub, month)

            run_record = sections.get("cost_sync_run")
            if isinstance(run_record, dict):
                _record_cost_sync_run(
                    db,
                    sub,
                    month,
                    str(run_record.get("mtd_start") or meta.get("mtd_start") or ""),
                    str(run_record.get("mtd_end") or meta.get("mtd_end") or ""),
                    run_record.get("current_services") or {},
                    run_record.get("service_changes"),
                    run_record.get("previous_synced_at"),
                    subscription_total_billing=float(run_record.get("subscription_total_billing") or 0.0),
                    subscription_total_usd=float(run_record.get("subscription_total_usd") or 0.0),
                    subscription_currency=str(run_record.get("subscription_currency") or "USD"),
                )
            db.commit()
    finally:
        db.close()


def _persist_metrics_data(
    envelope: JobEnvelope,
    data: dict[str, Any],
    run_params: dict[str, Any],
) -> None:
    from app.database import SessionLocal
    from app.models import ResourceSnapshot
    from app.pipeline.store import persist_normalized_snapshot

    sub = envelope.subscription_id
    sections = data.get("sections") or {}
    records = sections.get("metrics_records") or []

    db = SessionLocal()
    try:
        for record in records:
            resource_id = str(record.get("resource_id") or "")
            if not resource_id:
                continue
            resource = (
                db.query(ResourceSnapshot)
                .filter(
                    ResourceSnapshot.subscription_id == sub,
                    ResourceSnapshot.resource_id == resource_id,
                    ResourceSnapshot.is_active.is_(True),
                )
                .first()
            )
            if resource is None:
                log.warning(
                    "data_persist.metrics_missing_resource",
                    resource_id=resource_id,
                    pipeline_id=envelope.pipeline_id,
                )
                continue
            row_dict = record.get("row_dict") or {}
            facts = record.get("facts") or {}
            normalized_record = record.get("normalized_record")
            persist_normalized_snapshot(
                db,
                subscription_id=sub,
                row_dict=row_dict,
                metrics=facts,
                pipeline_stage="metrics_ready",
                normalized_record=normalized_record,
            )
            try:
                from app.data_store.resource_enrichment import upsert_metrics

                upsert_metrics(db, resource, facts)
            except Exception as exc:
                log.warning(
                    "data_persist.metrics_enrichment_failed",
                    resource_id=resource_id,
                    error=str(exc)[:200],
                )
        db.commit()
    finally:
        db.close()


def _persist_analysis_data(
    envelope: JobEnvelope,
    data: dict[str, Any],
    run_params: dict[str, Any],
) -> None:
    from app.analysis_persist import close_open_findings, persist_optimization_run
    from app.database import SessionLocal
    from app.models import AnalysisJob

    sub = envelope.subscription_id
    sections = data.get("sections") or {}
    analysis = sections.get("analysis") or {}
    result = analysis.get("result") or {}
    job_id = analysis.get("job_id")
    profile = str(analysis.get("profile") or run_params.get("profile") or "default")
    engine_version = str(analysis.get("engine_version") or run_params.get("engine_version") or "extended")
    scope_components = analysis.get("scope_components")
    scope_resource_types = analysis.get("scope_resource_types")

    db = SessionLocal()
    try:
        scoped_types = None
        if scope_resource_types:
            scoped_types = {str(t).strip().lower() for t in scope_resource_types if t}
        if scope_components and not scoped_types:
            from app.optimizer.component_map import resource_types_for_components

            scoped_types = resource_types_for_components(scope_components)

        if scope_components:
            close_open_findings(db, sub, components=scope_components)
        else:
            close_open_findings(db, sub)

        run_id = persist_optimization_run(
            db,
            subscription_id=sub,
            profile=profile,
            engine_version=engine_version,
            result=result,
            data_source="db",
            scope_resource_types=scoped_types,
        )
        result["run_id"] = run_id

        if job_id:
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if job:
                findings_count = result.get("summary", {}).get("total_findings", 0)
                savings_usd = result.get("summary", {}).get("total_estimated_monthly_savings_usd", 0.0)
                from app.batch_analyzer import _mark_job_components_completed

                _mark_job_components_completed(job, findings_count, savings_usd)
                job.run_id = run_id
                job.status = "completed"
                job.progress_pct = 100
                job.completed_batches = job.total_batches or 1
                job.current_component = None
                from datetime import datetime, timezone

                job.completed_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()
