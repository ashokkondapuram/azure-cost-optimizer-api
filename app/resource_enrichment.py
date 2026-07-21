"""Unified resource enrichment — facade over per-type ``resource_enrichment_*`` tables.

Primary store: ``app.data_store.resource_enrichment`` (one row per resource, table per type).
Pipeline snapshots live on the same enrichment row via ``snapshot_json`` and ``pipeline_stage``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.assessment.normalizer import build_normalized_record, merge_snapshot_json, resource_row_to_dict
from app.data_store import resource_enrichment as enrichment_store
from app.focus_mapping import normalize_arm_id
from app.models import ResourceSnapshot
from app.pipeline.store import get_or_create_snapshot, load_snapshot_dict

_UTILIZATION_FACT_KEYS = frozenset({
    "avg_cpu_pct",
    "avg_cpu",
    "cpu_pct",
    "max_cpu_pct",
    "memory_pct",
    "avg_memory_pct",
    "avg_mem_pct",
    "memory_usage_pct",
    "cluster_cpu_pct",
    "cluster_mem_pct",
    "normalized_ru_pct",
    "storage_pct",
    "disk_iops_utilization_pct",
    "disk_throughput_utilization_pct",
    "peak_disk_iops_utilization_pct",
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enrichment_max_age_hours() -> float:
    return max(0.25, float(os.getenv("ENRICHMENT_MAX_AGE_HOURS", "6")))


def _strip_heavy_payload_fields(payload: dict[str, Any]) -> dict[str, Any]:
    slim = dict(payload)
    slim.pop("metrics_raw", None)
    return slim


def _is_fresh(fresh_at: datetime | None, *, max_age_hours: float | None = None) -> bool:
    if fresh_at is None:
        return False
    ts = fresh_at.replace(tzinfo=timezone.utc) if fresh_at.tzinfo is None else fresh_at.astimezone(timezone.utc)
    return (_now() - ts) <= timedelta(hours=max_age_hours or enrichment_max_age_hours())


def _inventory_row_dict(db: Session, resource_id: str) -> dict[str, Any] | None:
    rid = normalize_arm_id(resource_id)
    row = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.resource_id == rid,
            ResourceSnapshot.is_active.is_(True),
        )
        .first()
    )
    if not row:
        return None
    return resource_row_to_dict(row)


def _snapshot_for_arm(db: Session, resource_id: str) -> ResourceSnapshot | None:
    rid = normalize_arm_id(resource_id)
    return (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.resource_id == rid,
            ResourceSnapshot.is_active.is_(True),
        )
        .first()
    )


def get_enrichment_row(
    db: Session,
    subscription_id: str,
    resource_id: str,
):
    return enrichment_store.get_enrichment_row(db, subscription_id, resource_id)


def load_metrics_payload_from_enrichment(
    db: Session,
    resource_id: str,
    *,
    max_age_hours: float | None = None,
) -> dict[str, Any] | None:
    """Return cached metrics API payload when fresh enough."""
    age_hours = max_age_hours if max_age_hours is not None else enrichment_max_age_hours()
    try:
        return enrichment_store.load_metrics_payload_from_store(
            db, resource_id, max_age_hours=age_hours,
        )
    except Exception:
        return None


def persist_metrics_enrichment(
    db: Session,
    *,
    subscription_id: str,
    row_dict: dict[str, Any],
    metrics_payload: dict[str, Any],
    facts: dict[str, Any] | None = None,
    monitor_raw: dict[str, Any] | None = None,
) -> None:
    """Write metrics to per-type enrichment after Azure Monitor fetch."""
    snapshot = _snapshot_for_arm(db, row_dict["resource_id"])
    flat_facts = facts if facts is not None else (metrics_payload.get("facts") or {})
    if snapshot:
        enrichment_store.upsert_metrics(
            db,
            snapshot,
            flat_facts,
            metrics_payload=metrics_payload,
            monitor_raw=monitor_raw,
        )

    snap = get_or_create_snapshot(
        db,
        subscription_id=subscription_id,
        resource_id=row_dict["resource_id"],
        resource_type=row_dict.get("resource_type") or "",
        canonical_type=row_dict.get("canonical_type"),
    )
    existing = load_snapshot_dict(snap)
    from app.assessment.catalog import get_assessment_for_arm_type

    arm_type = row_dict.get("resource_type") or ""
    assessment = get_assessment_for_arm_type(arm_type)
    record = build_normalized_record(
        row_dict,
        metrics=flat_facts,
        assessment=assessment,
        metrics_payload=metrics_payload,
        monitor_raw=monitor_raw,
    )
    merged = merge_snapshot_json(existing, record)
    merged["metrics_payload"] = _strip_heavy_payload_fields(metrics_payload)
    merged["metrics_timespan"] = metrics_payload.get("timespan")
    snap.snapshot_json = json.dumps(merged)
    snap.metrics_at = _now()
    snap.enriched_at = _now()
    if (snap.pipeline_stage or "pending") == "pending":
        snap.pipeline_stage = "metrics_ready"
    snap.updated_at = _now()


def persist_monitor_batch_results(
    db: Session,
    subscription_id: str,
    resources: list[dict[str, Any]],
    resource_facts: dict[str, dict[str, Any]],
    *,
    timespan: str | None = None,
    resource_metrics: dict[str, dict[str, Any]] | None = None,
) -> int:
    """Persist monitor facts and optional raw payloads from a batch Azure Monitor fetch."""
    from app.assessment.normalizer import resource_row_to_dict

    sub = subscription_id.strip().lower()
    ts = timespan or "P7D"
    metrics_by_rid = resource_metrics or {}
    written = 0

    for resource in resources:
        rid = normalize_arm_id(resource.get("id") or "")
        if not rid:
            continue
        facts = resource_facts.get(rid.lower()) or {}
        monitor_raw = metrics_by_rid.get(rid.lower())
        if not facts and not monitor_raw:
            continue

        row = (
            db.query(ResourceSnapshot)
            .filter(
                ResourceSnapshot.subscription_id == sub,
                ResourceSnapshot.resource_id == rid,
                ResourceSnapshot.is_active.is_(True),
            )
            .first()
        )
        if not row:
            continue

        row_dict = resource_row_to_dict(row)
        payload = {
            "ok": True,
            "resource_id": rid,
            "canonical_type": row_dict.get("canonical_type"),
            "timespan": ts,
            "data_quality": "azure_monitor",
            "facts": facts,
            "metrics": [],
            "derived": [],
        }
        try:
            persist_metrics_enrichment(
                db,
                subscription_id=sub,
                row_dict=row_dict,
                metrics_payload=payload,
                facts=facts,
                monitor_raw=monitor_raw,
            )
            written += 1
        except Exception as exc:
            import structlog
            structlog.get_logger().warning(
                "batch_metrics_enrichment_persist_failed",
                resource_id=rid,
                error=str(exc)[:200],
            )
    return written


def persist_properties_enrichment(
    db: Session,
    *,
    subscription_id: str,
    row_dict: dict[str, Any],
) -> None:
    """Refresh properties/cost block after inventory sync."""
    snapshot = _snapshot_for_arm(db, row_dict["resource_id"])
    if snapshot:
        from app.cost_db import resource_cost_map_from_db
        from app.focus_mapping import normalize_arm_id

        enrichment_store.upsert_properties(db, snapshot)
        sub = subscription_id.strip().lower()
        cost_map = resource_cost_map_from_db(db, sub)
        arm = normalize_arm_id(snapshot.resource_id)
        overlay = cost_map.get(arm) if arm else None
        enrichment_store.upsert_cost(db, snapshot, cost_overlay=overlay)

    snap = get_or_create_snapshot(
        db,
        subscription_id=subscription_id,
        resource_id=row_dict["resource_id"],
        resource_type=row_dict.get("resource_type") or "",
        canonical_type=row_dict.get("canonical_type"),
    )
    existing = load_snapshot_dict(snap)
    record = build_normalized_record(row_dict)
    merged = merge_snapshot_json(existing, record)
    snap.snapshot_json = json.dumps(merged)
    snap.cost_at = _now()
    snap.enriched_at = _now()
    snap.updated_at = _now()


def persist_recommendations_enrichment(
    db: Session,
    *,
    subscription_id: str,
    resource_id: str,
    summary: list[dict[str, Any]],
    findings_count: int = 0,
    savings_usd: float = 0.0,
    top_severity: str | None = None,
) -> None:
    """Write analysis recommendations onto the enrichment row."""
    snapshot = _snapshot_for_arm(db, resource_id)
    if snapshot:
        enrichment_store.upsert_recommendations(
            db,
            snapshot,
            summary=summary,
            findings_count=findings_count,
            savings_usd=savings_usd,
            top_severity=top_severity,
        )

    row_dict = _inventory_row_dict(db, resource_id)
    if not row_dict:
        return
    snap = get_or_create_snapshot(
        db,
        subscription_id=subscription_id,
        resource_id=row_dict["resource_id"],
        resource_type=row_dict.get("resource_type") or "",
        canonical_type=row_dict.get("canonical_type"),
    )
    existing = load_snapshot_dict(snap)
    existing["recommendations"] = {
        "summary": summary,
        "findings_count": findings_count,
        "savings_usd": savings_usd,
        "top_severity": top_severity,
    }
    snap.snapshot_json = json.dumps(existing)
    snap.analysis_at = _now()
    snap.enriched_at = _now()
    snap.updated_at = _now()


def load_enrichment_batch(
    db: Session,
    subscription_id: str,
    resource_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Batch-load enrichment keyed by lowercased ARM id."""
    try:
        primary = enrichment_store.load_enrichment_batch(db, subscription_id, resource_ids)
    except Exception:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for arm, payload in primary.items():
        out[arm] = {
            "snapshot": {
                "metrics_payload": (payload.get("metrics") or {}).get("payload"),
                "metrics": payload.get("metrics"),
                "recommendations": payload.get("recommendations"),
                "cost": payload.get("cost"),
                "properties": payload.get("properties"),
                "assessment_properties": payload.get("assessment_properties"),
                "assessment_property_rows": payload.get("assessment_property_rows"),
            },
            "metrics_fresh_at": payload.get("metrics_at"),
            "cost_fresh_at": payload.get("cost_at"),
            "analysis_fresh_at": payload.get("analysis_at"),
            "enriched_at": payload.get("enriched_at"),
        }
    return out


def enrichment_drawer_entry(
    enrichment: dict[str, Any] | None,
    *,
    include_metrics: bool,
    include_recommendations: bool,
) -> dict[str, Any]:
    if not enrichment:
        return {}
    if "snapshot" in enrichment and "cost" not in enrichment:
        snap = enrichment.get("snapshot") or {}
        enrichment = {
            "metrics": snap.get("metrics"),
            "recommendations": snap.get("recommendations"),
            "cost": snap.get("cost"),
        }
    return enrichment_store.enrichment_drawer_entry(
        enrichment,
        include_metrics=include_metrics,
        include_recommendations=include_recommendations,
    )


def extract_facts_from_snapshot(snap: dict[str, Any]) -> dict[str, Any]:
    """Flatten utilization facts from a persisted enrichment snapshot."""
    payload = snap.get("metrics_payload") or {}
    facts = payload.get("facts") if isinstance(payload, dict) else {}
    if not isinstance(facts, dict):
        facts = {}
    if facts:
        return facts
    metrics = snap.get("metrics") or {}
    if isinstance(metrics, dict):
        inner = metrics.get("utilization") or {}
        if isinstance(inner, dict):
            return {**metrics, **inner}
        return metrics
    return {}


def _utilization_pct_from_facts(facts: dict[str, Any]) -> float | None:
    for key in _UTILIZATION_FACT_KEYS:
        if key not in facts:
            continue
        try:
            pct = float(facts[key])
        except (TypeError, ValueError):
            continue
        if key.endswith("_pct") or key in {"avg_cpu_pct", "max_cpu_pct", "memory_pct", "avg_memory_pct"}:
            if pct <= 1.0:
                pct *= 100.0
        return pct
    return None


def utilization_display_from_facts(facts: dict[str, Any]) -> str | None:
    pct = _utilization_pct_from_facts(facts)
    if pct is None:
        return None
    return f"{pct:.1f}%"


def utilization_map_from_enrichment(
    db: Session,
    subscription_id: str,
    resource_ids: list[str],
) -> dict[str, str]:
    """Per-resource utilization labels for dashboard panels."""
    batch = load_enrichment_batch(db, subscription_id, resource_ids)
    out: dict[str, str] = {}
    for rid_key, enrichment in batch.items():
        if not _is_fresh(enrichment.get("metrics_fresh_at")):
            continue
        snap = enrichment.get("snapshot") or {}
        label = utilization_display_from_facts(extract_facts_from_snapshot(snap))
        if label:
            out[normalize_arm_id(rid_key)] = label
    return out


def mtd_costs_map_from_enrichment(
    db: Session,
    subscription_id: str,
    resource_ids: list[str],
) -> dict[str, float]:
    """MTD cost per resource from enrichment cost blocks."""
    from app.cost_utils import monthly_cost_amounts_from_cost_block

    batch = load_enrichment_batch(db, subscription_id, resource_ids)
    out: dict[str, float] = {}
    for rid_key, enrichment in batch.items():
        snap = enrichment.get("snapshot") or {}
        cost = snap.get("cost")
        if not isinstance(cost, dict):
            continue
        billing, usd, _currency = monthly_cost_amounts_from_cost_block(cost)
        amount = billing if billing > 0 else usd
        if amount > 0:
            out[normalize_arm_id(rid_key)] = round(amount, 2)
    return out


def _merge_assessment_properties_into_row(
    row: dict[str, Any],
    assessment_props: dict[str, Any],
    *,
    property_rows: list[dict[str, Any]] | None = None,
) -> None:
    """Overlay flat assessment properties onto list/detail rows."""
    if not assessment_props:
        return
    flat_props = assessment_props
    nested_rows = property_rows
    if isinstance(assessment_props.get("flat"), dict):
        flat_props = assessment_props.get("flat") or {}
        nested_rows = nested_rows or assessment_props.get("rows")
    row["assessment_properties"] = flat_props
    if nested_rows:
        row["property_rows"] = nested_rows
    props = row.get("properties")
    merged_props = dict(props) if isinstance(props, dict) else {}
    int_keys = {"diskSizeGB", "diskIOPSReadWrite", "diskMBpsReadWrite"}
    bool_keys = {"burstingEnabled", "optimizedForFrequentAttach", "supportsHibernation"}
    for key, val in flat_props.items():
        if val is None:
            continue
        if key in int_keys:
            try:
                merged_props[key] = int(val) if str(val).isdigit() else float(val)
                continue
            except (TypeError, ValueError):
                pass
        if key in bool_keys and isinstance(val, str):
            merged_props[key] = val.lower() in {"yes", "true", "1"}
            continue
        merged_props[key] = val
    row["properties"] = merged_props


def overlay_list_rows_from_enrichment(
    db: Session,
    subscription_id: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Optional list overlay: cost + metricsFacts + assessment properties from enrichment."""
    if not rows:
        return rows
    ids = [row.get("id") or row.get("resource_id") or "" for row in rows]
    batch = load_enrichment_batch(db, subscription_id, ids)
    if not batch:
        return rows
    for row in rows:
        rid = normalize_arm_id(row.get("id") or row.get("resource_id") or "")
        if not rid:
            continue
        enrichment = batch.get(rid)
        if not enrichment:
            continue
        snap = enrichment.get("snapshot") or {}
        assessment_props = snap.get("assessment_properties") or {}
        if assessment_props:
            _merge_assessment_properties_into_row(
                row,
                assessment_props,
                property_rows=snap.get("assessment_property_rows"),
            )
        cost = snap.get("cost")
        if isinstance(cost, dict):
            from app.cost_utils import (
                attach_cost_envelope_to_row,
                build_resource_cost_envelope,
                monthly_cost_amounts_from_cost_block,
                monthly_cost_amounts_from_row,
            )

            row_billing, row_usd = monthly_cost_amounts_from_row(row)
            enrich_billing, enrich_usd, currency = monthly_cost_amounts_from_cost_block(cost)
            billing = enrich_billing if enrich_billing > 0 else row_billing
            usd = enrich_usd if enrich_usd > 0 else row_usd
            if billing <= 0 and row_billing > 0:
                billing = row_billing
            if usd <= 0 and row_usd > 0:
                usd = row_usd
            if currency:
                row["billingCurrency"] = currency
            if billing > 0:
                row["monthlyCostBilling"] = billing
            if usd > 0:
                row["monthlyCostUsd"] = usd
            attach_cost_envelope_to_row(
                row,
                build_resource_cost_envelope(
                    billing=billing,
                    usd=usd,
                    currency=currency or row.get("billingCurrency") or "CAD",
                    retail_monthly=cost.get("retail_monthly"),
                    retail_currency=cost.get("retail_currency"),
                    retail_source=cost.get("retail_source"),
                    retail_pending=cost.get("retail_pending"),
                    cost_pending=not (billing > 0 or usd > 0),
                ),
            )
        if _is_fresh(enrichment.get("metrics_fresh_at")):
            facts = extract_facts_from_snapshot(snap)
            if facts:
                row["metricsFacts"] = {
                    k: facts[k]
                    for k in sorted(facts)
                    if k in _UTILIZATION_FACT_KEYS and facts[k] is not None
                }
                existing_metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
                merged_metrics = {**facts, **existing_metrics}
                row["metrics"] = merged_metrics
                row["_metrics"] = merged_metrics
                row["_technical_facts"] = {**(row.get("_technical_facts") or {}), **facts}
    return rows


def advanced_analysis_from_enrichment(
    enrichment: dict[str, Any] | None,
    *,
    slim: bool = True,
) -> dict[str, Any] | None:
    """Drawer advanced_analysis payload from persisted recommendations."""
    if not enrichment:
        return None
    if not _is_fresh(enrichment.get("analysis_fresh_at")):
        return None
    snap = enrichment.get("snapshot") or {}
    stored = snap.get("advanced_analysis")
    if isinstance(stored, dict) and stored:
        if slim:
            from app.drawer_payload import slim_analysis_payload

            return slim_analysis_payload(stored)
        return stored
    recs = snap.get("recommendations")
    if not isinstance(recs, dict):
        return None
    summary = recs.get("summary") or []
    if not summary:
        return None
    findings_count = int(recs.get("findings_count") or len(summary))
    savings = float(recs.get("savings_usd") or 0)
    severity = (recs.get("top_severity") or "").strip()
    headline_parts: list[str] = []
    if severity:
        headline_parts.append(f"{severity.title()} severity")
    if findings_count:
        headline_parts.append(
            f"{findings_count} open finding{'s' if findings_count != 1 else ''}"
        )
    if savings > 0:
        headline_parts.append(f"${savings:,.0f}/mo potential savings")
    insights = {
        "headline": " · ".join(headline_parts) or "Optimization findings available",
        "finding_summaries": summary[:5],
        "estimated_savings_usd": savings,
    }
    payload = {"insights": insights, "trends": None}
    if slim:
        from app.drawer_payload import slim_analysis_payload

        return slim_analysis_payload(payload)
    return payload


def utilization_by_type_from_enrichment(
    db: Session,
    subscription_id: str,
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Dashboard utilization chart from persisted enrichment metrics."""
    return enrichment_store.utilization_by_type_from_enrichment(
        db, subscription_id, limit=limit,
    )
