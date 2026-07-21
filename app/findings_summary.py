"""Aggregated optimization finding counts for dashboards and filter tabs."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import OptimizationFinding
from app.analysis_persist import dedupe_open_findings_for_display
from app.recommendation_execution import implemented_findings_for_subscription
from app.finding_taxonomy import (
    build_ordered_breakdown,
    format_category_label,
    format_severity_label,
    format_source_label,
)
from app.savings_aggregation import aggregate_subscription_savings, aggregate_findings_savings, unified_savings_by_resource_engine
from app.focus_mapping import normalize_arm_id
from app.resource_store import _inventory_id_set
from app.finding_aggregation import aggregate_findings_by_resource

# Rightsizing rules remain cost optimization even when retail savings are not quantified.
COST_OPTIMIZATION_RULE_IDS = frozenset({
    "VM_SKU_SIZING_EXTENDED",
    "VM_RIGHTSIZE_FAMILY",
    "VM_UNDERUTILIZED_EXTENDED",
    "VM_OVERSIZE",
    "VM_UNDERUTILIZED",
    "REDIS_RIGHTSIZE_EXTENDED",
})

def _normalize_sub(subscription_id: str | None) -> str | None:
    if not subscription_id:
        return None
    return subscription_id.strip().lower()


def _evidence_dict(raw: Any) -> dict[str, Any]:
    import json

    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _summary_field(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


def classify_finding_source(finding: Any) -> str:
    """Bucket an open finding for Action centre breakdown (sums to action-centre total)."""
    rule_id = str(_summary_field(finding, "rule_id") or "").lower()
    evidence = _evidence_dict(
        _summary_field(finding, "evidence_json")
        if not isinstance(finding, dict)
        else finding.get("evidence")
    )
    engine = str(evidence.get("engine") or evidence.get("rule_source") or "").lower()

    if rule_id.startswith("advisor_") or engine == "azure_advisor":
        return "reliability_security"

    category = str(_summary_field(finding, "category") or "").upper()
    if category in {"RELIABILITY", "SECURITY"}:
        return "reliability_security"
    if category == "GOVERNANCE" or rule_id.startswith("governance_"):
        return "governance"
    return "cost_performance"


def _count_by_source(findings: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in findings:
        key = classify_finding_source(row)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _resources_with_findings(findings: list[Any]) -> int:
    seen: set[str] = set()
    for row in findings:
        rid = normalize_arm_id(getattr(row, "resource_id", None) or "")
        if rid:
            seen.add(rid)
    return len(seen)


def _filter_findings_to_inventory(
    db: Session,
    subscription_id: str,
    findings: list[OptimizationFinding],
) -> list[OptimizationFinding]:
    inv_ids = _inventory_id_set(db, subscription_id)
    if not inv_ids:
        return []
    kept: list[OptimizationFinding] = []
    for row in findings:
        rid = normalize_arm_id(row.resource_id)
        if rid and rid in inv_ids:
            kept.append(row)
    return kept


def build_findings_summary(
    db: Session,
    subscription_id: str | None = None,
    *,
    inventory_only: bool = False,
) -> dict[str, Any]:
    """Return counts by status, severity, category, and savings type."""
    filt: list = []
    sub = _normalize_sub(subscription_id)
    if sub:
        filt.append(func.lower(OptimizationFinding.subscription_id) == sub)

    def _q():
        q = db.query(OptimizationFinding)
        if filt:
            q = q.filter(*filt)
        return q

    total = _q().count() or 0  # raw rows in DB (includes superseded resolved history)

    by_status_raw = dict(
        db.query(OptimizationFinding.status, func.count(OptimizationFinding.id))
        .filter(*filt)
        .group_by(OptimizationFinding.status)
        .all()
    )

    open_filt = [*filt, OptimizationFinding.status == "open"]
    open_rows = (
        db.query(OptimizationFinding)
        .filter(*open_filt)
        .all()
    )
    deduped_open_all = dedupe_open_findings_for_display(open_rows)
    from app.finding_quality import filter_action_centre_findings, is_action_centre_finding

    inventory_ids = _inventory_id_set(db, sub) if sub else set()
    if sub and (inventory_only or inventory_ids):
        inventory_open = _filter_findings_to_inventory(db, sub, deduped_open_all)
        action_centre_open = filter_action_centre_findings(inventory_open)
    else:
        action_centre_open = filter_action_centre_findings(deduped_open_all)
    aggregated_action_centre_open = aggregate_findings_by_resource(action_centre_open)
    if inventory_only and sub:
        deduped_open = action_centre_open
    else:
        deduped_open = deduped_open_all
    open_count_all = len(deduped_open_all)
    action_centre_count = len(aggregated_action_centre_open)
    open_count = action_centre_count if sub else open_count_all

    excluded_metric_gaps = sum(
        1 for f in deduped_open_all if not is_action_centre_finding(f)
    )
    excluded_cost_export = 0
    if sub and inventory_ids:
        excluded_cost_export = sum(
            1 for f in deduped_open_all
            if is_action_centre_finding(f)
            and normalize_arm_id(f.resource_id) not in inventory_ids
        )

    by_source = _count_by_source(aggregated_action_centre_open)
    by_source_ordered = build_ordered_breakdown(by_source, kind="source")

    # Severity and category breakdowns scoped to Action centre open findings (one row per resource)
    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    savings_by_severity: dict[str, float] = {}
    savings_by_category: dict[str, float] = {}
    breakdown_rows = aggregated_action_centre_open if sub else deduped_open
    savings_rows = action_centre_open if sub else deduped_open
    for f in breakdown_rows:
        sev = str(_summary_field(f, "severity") or "INFO").upper()
        cat = str(_summary_field(f, "category") or "OTHER").upper()
        savings = float(_summary_field(f, "estimated_savings_usd") or 0)
        by_severity[sev] = by_severity.get(sev, 0) + 1
        by_category[cat] = by_category.get(cat, 0) + 1
        savings_by_severity[sev] = savings_by_severity.get(sev, 0) + savings
        savings_by_category[cat] = savings_by_category.get(cat, 0) + savings

    acknowledged_count = int(by_status_raw.get("acknowledged") or 0)
    ignored_count = int(by_status_raw.get("ignored") or 0)
    implemented_count = len(implemented_findings_for_subscription(db, sub or "")) if sub else 0
    by_status = {
        "open": open_count,
        "acknowledged": acknowledged_count,
        "implemented": implemented_count,
        "ignored": ignored_count,
    }
    total_display = open_count + acknowledged_count + implemented_count + ignored_count

    total_savings = round(
        sum(float(_summary_field(f, "estimated_savings_usd") or 0) for f in breakdown_rows),
        2,
    )

    unified = aggregate_subscription_savings(db, sub or "") if sub else {}
    engine_rollup = aggregate_findings_savings(savings_rows)
    savings_by_resource = unified_savings_by_resource_engine(savings_rows)
    unified_total = float(
        unified.get("unified_estimated_monthly_savings")
        or engine_rollup.get("total_estimated_savings_usd")
        or total_savings
    )

    def _is_cost_optimization_row(row: Any) -> bool:
        if float(_summary_field(row, "estimated_savings_usd") or 0) > 0:
            return True
        rule_id = _summary_field(row, "rule_id")
        if rule_id in COST_OPTIMIZATION_RULE_IDS:
            return True
        evidence = _summary_field(row, "evidence_json") if not isinstance(row, dict) else row.get("evidence")
        evidence_text = evidence if isinstance(evidence, str) else str(evidence or "")
        return '"sizing_action": "cross_family"' in evidence_text or '"sizing_action": "downgrade"' in evidence_text

    with_savings_count = sum(
        1 for f in breakdown_rows if float(_summary_field(f, "estimated_savings_usd") or 0) > 0
    )
    cost_optimization_count = sum(1 for f in savings_rows if _is_cost_optimization_row(f))
    governance_count = int(by_source.get("governance") or 0)

    return {
        "total_findings": int(total_display),
        "open_findings": int(open_count),
        "open_findings_all": int(open_count_all),
        "action_centre_open_findings": int(action_centre_count),
        "resources_with_findings": _resources_with_findings(action_centre_open),
        "by_source": by_source,
        "by_source_ordered": by_source_ordered,
        "source_labels": {k: format_source_label(k) for k in by_source},
        "excluded": {
            "metric_gaps": int(excluded_metric_gaps),
            "cost_export_only": int(excluded_cost_export),
            "total": int(excluded_metric_gaps + excluded_cost_export),
        },
        "total_estimated_savings_usd": round(unified_total, 2),
        "raw_total_estimated_savings_usd": round(float(total_savings), 2),
        "engine_unified_savings_usd": float(engine_rollup.get("total_estimated_savings_usd") or 0),
        "savings_by_resource_usd": savings_by_resource,
        "unified_savings": unified,
        "by_status": {str(k or "unknown"): int(v) for k, v in by_status.items()},
        "by_severity": by_severity,
        "by_category": by_category,
        "by_severity_ordered": build_ordered_breakdown(
            by_severity,
            savings=savings_by_severity,
            kind="severity",
        ),
        "by_category_ordered": build_ordered_breakdown(
            by_category,
            savings=savings_by_category,
            kind="category",
        ),
        "severity_labels": {k: format_severity_label(k) for k in by_severity},
        "category_labels": {k: format_category_label(k) for k in by_category},
        "open_count": int(open_count),
        "total_open": int(open_count),
        "governance_findings": int(governance_count),
        "with_savings_findings": int(with_savings_count),
        "cost_optimization_findings": int(cost_optimization_count),
        "inventory_only": bool(inventory_only),
    }
