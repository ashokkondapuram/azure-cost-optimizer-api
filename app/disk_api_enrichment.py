"""Enrich managed-disk list/detail API rows to match disk-assessment v2 (concept v2) shape.

Canonical response contract (list + detail after enrichment):
- assessment_properties: flat EAV assessment fields from enrichment store
- property_rows: structured EAV rows (property_key, property_value, label, group_key)
- properties: merged ARM properties + assessment_properties (diskSizeGB, diskState, …)
- metrics / _metrics: flat monitor facts (disk_iops_utilization_pct, disk_read_bps, …)
- cost: { billed_mtd, retail_monthly, retail_currency, retail_source, savings_estimate }
- finding: { rule_id, severity, savings, workflow, source } | null
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.cost_utils import attach_cost_envelope_to_row, build_resource_cost_envelope
from app.focus_mapping import normalize_arm_id
from app.resource_retail_cost import estimate_resource_retail_monthly


def _as_dict(value: Any) -> dict[str, Any]:
    """Coerce API row fragments to dict — list endpoints must not 500 on bad shapes."""
    if isinstance(value, dict):
        return dict(value)
    return {}


def _flatten_assessment_properties(value: Any) -> dict[str, Any]:
    """Accept flat EAV dict or persisted {flat, rows} envelope."""
    raw = _as_dict(value)
    nested_flat = raw.get("flat")
    if isinstance(nested_flat, dict):
        return dict(nested_flat)
    return raw


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _metrics_fact_sources(row: dict[str, Any]) -> dict[str, Any]:
    """Merge persisted monitor facts from all row shapes used by list/detail APIs."""
    merged: dict[str, Any] = {}
    for block in (
        row.get("metricsFacts"),
        row.get("_technical_facts"),
        row.get("metrics"),
        row.get("_metrics"),
    ):
        if isinstance(block, dict):
            for key, val in block.items():
                if val is not None and key not in merged:
                    merged[key] = val
    return merged


def _row_metrics_block(row: dict[str, Any]) -> dict[str, Any]:
    """Build flat metrics block from enrichment facts, _metrics, or derived utilization."""
    from app.disk_utilization import (
        disk_iops_utilization_pct,
        disk_throughput_utilization_pct,
        peak_disk_iops_utilization_pct,
        metrics_status,
        check_metric_staleness,
    )
    from app.resource_utilization import fact_value

    fact_sources = _metrics_fact_sources(row)
    if fact_sources and not row.get("_technical_facts"):
        row["_technical_facts"] = dict(fact_sources)

    metrics: dict[str, Any] = dict(fact_sources)

    if metrics.get("disk_iops_utilization_pct") is not None and metrics.get("disk_throughput_utilization_pct") is not None:
        return metrics

    iops_util = disk_iops_utilization_pct(row, row)
    if iops_util is not None:
        metrics["disk_iops_utilization_pct"] = round(iops_util, 2)

    throughput_util = disk_throughput_utilization_pct(row, row)
    if throughput_util is not None:
        metrics["disk_throughput_utilization_pct"] = round(throughput_util, 2)

    peak_iops_util = peak_disk_iops_utilization_pct(row, row)
    if peak_iops_util is not None:
        metrics["peak_disk_iops_utilization_pct"] = round(peak_iops_util, 2)

    for metric_key in (
        "disk_read_iops",
        "disk_write_iops",
        "disk_read_bps",
        "disk_write_bps",
        "disk_paid_burst_iops",
        "disk_queue_depth",
        "disk_used_pct",
    ):
        val = fact_value(row, metric_key)
        if val is not None:
            metrics[metric_key] = round(val, 2) if isinstance(val, float) else val

    if metrics:
        metrics["metrics_status"] = metrics_status(row)
        staleness_warning = check_metric_staleness(row)
        if staleness_warning:
            metrics["staleness_warning"] = staleness_warning

    return metrics


def _normalize_disk_properties(row: dict[str, Any]) -> dict[str, Any]:
    """Flatten sku/tier into properties block as concept v2 sample data expects."""
    assessment = _flatten_assessment_properties(row.get("assessment_properties"))
    props = _as_dict(row.get("properties"))
    if assessment:
        for key, val in assessment.items():
            if key in {"flat", "rows"}:
                continue
            if val is not None and props.get(key) in (None, ""):
                props[key] = val
    sku = row.get("sku")
    if isinstance(sku, dict):
        sku = sku.get("name") or sku.get("tier")
    if sku and not props.get("sku"):
        props["sku"] = sku
    if isinstance(row.get("sku"), str) and row.get("sku"):
        row["sku"] = {"name": row["sku"]}
    sku_details = row.get("skuDetails") or {}
    if not props.get("tier"):
        props["tier"] = props.get("tier") or sku_details.get("tier") or ""
    if props.get("diskSizeGB") is None and sku_details.get("size"):
        try:
            props["diskSizeGB"] = int(sku_details["size"])
        except (TypeError, ValueError):
            pass
    row["properties"] = props
    return props


def _ensure_cost_block(row: dict[str, Any], db: Session | None = None) -> dict[str, Any]:
    """Ensure nested cost{} with billed_mtd, retail_monthly, savings_estimate."""
    existing = row.get("cost") if isinstance(row.get("cost"), dict) else {}
    billing = _safe_float(
        row.get("monthlyCostBilling") or row.get("monthly_cost_billing") or existing.get("billed_mtd")
    )
    usd = _safe_float(row.get("monthlyCostUsd") or row.get("monthly_cost_usd"))
    currency = str(row.get("billingCurrency") or row.get("billing_currency") or existing.get("billed_currency") or "CAD")

    retail_monthly = existing.get("retail_monthly") or row.get("retailMonthly") or row.get("retail_monthly")
    retail_currency = existing.get("retail_currency") or row.get("retailCurrency") or row.get("retail_currency")
    retail_source = existing.get("retail_source") or row.get("retailSource") or row.get("retail_source")
    retail_pending = existing.get("retail_pending")

    if retail_monthly is None and not retail_source:
        retail_payload = estimate_resource_retail_monthly(row, db)
        retail_monthly = retail_payload.get("retail_monthly")
        retail_currency = retail_payload.get("retail_currency") or currency
        retail_source = retail_payload.get("retail_source")
        retail_pending = retail_payload.get("retail_pending")

    savings_estimate = existing.get("savings_estimate")
    if savings_estimate is None:
        savings_estimate = _safe_float(
            row.get("analysisSavingsUsd") or row.get("analysis_savings_usd")
        ) or None

    envelope = build_resource_cost_envelope(
        billing=billing,
        usd=usd,
        currency=currency,
        retail_monthly=_safe_float(retail_monthly) if retail_monthly is not None else None,
        retail_currency=str(retail_currency) if retail_currency else currency,
        retail_source=str(retail_source) if retail_source else None,
        retail_pending=bool(retail_pending) if retail_pending is not None else retail_monthly is None,
        cost_pending=not (billing > 0 or usd > 0),
    )
    if savings_estimate is not None and float(savings_estimate) > 0:
        envelope["savings_estimate"] = round(float(savings_estimate), 2)
    attach_cost_envelope_to_row(row, envelope)
    return row["cost"]


def _finding_summary(row: dict[str, Any]) -> dict[str, Any] | None:
    """Compact per-row finding for list table (concept v2 finding block)."""
    summary = row.get("analysisSummary") or row.get("analysis_summary") or []
    if not isinstance(summary, list) or not summary:
        count = int(row.get("analysisFindingsCount") or row.get("analysis_findings_count") or 0)
        if count <= 0:
            return None
        severity = str(row.get("analysisTopSeverity") or row.get("analysis_top_severity") or "medium").lower()
        savings = float(row.get("analysisSavingsUsd") or row.get("analysis_savings_usd") or 0)
        return {
            "rule_id": None,
            "severity": severity,
            "savings": round(savings, 2),
            "workflow": "proposed",
            "source": "engine",
        }

    top = summary[0]
    if not isinstance(top, dict):
        return None
    severity = str(top.get("severity") or row.get("analysisTopSeverity") or "medium").lower()
    savings = float(top.get("estimated_savings_usd") or row.get("analysisSavingsUsd") or 0)
    return {
        "rule_id": top.get("rule_id"),
        "severity": severity,
        "savings": round(savings, 2),
        "workflow": "proposed",
        "source": "engine",
    }


def enrich_disk_api_row(row: dict[str, Any], *, include_metrics: bool = True, db: Session | None = None) -> dict[str, Any]:
    """Apply concept-v2 disk row shape: properties, metrics, cost, finding."""
    if not row or not isinstance(row, dict):
        return row
    canonical = str(row.get("type") or row.get("canonical_type") or "").strip().lower()
    arm = normalize_arm_id(row.get("id") or row.get("resource_id") or "")
    if canonical not in {"compute/disk", "microsoft.compute/disks"} and "/disks/" not in arm.lower():
        return row

    try:
        _normalize_disk_properties(row)
        _ensure_cost_block(row, db)

        if include_metrics:
            metrics = _row_metrics_block(row)
            if metrics:
                row["metrics"] = metrics
                row["_metrics"] = metrics

        finding = _finding_summary(row)
        row["finding"] = finding
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "disk_enrichment_failed",
            extra={"resource_id": row.get("id") or row.get("resource_id")},
        )

    return row


def enrich_disk_api_rows(rows: list[dict[str, Any]], *, include_metrics: bool = True, db: Session | None = None) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return rows
    for row in rows:
        try:
            enrich_disk_api_row(row, include_metrics=include_metrics, db=db)
        except Exception:
            continue
    return rows
