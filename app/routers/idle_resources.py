"""Unified idle resource sweep — aggregate idle/stale resources across all resource types."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.focus_mapping import normalize_arm_id
from app.idle_resource_rules import (
    OPEN_IDLE_STATUSES,
    heatmap_category,
    is_idle_or_waste_rule,
    load_resource_costs_usd,
    normalize_severity,
    resolve_finding_savings_usd,
)
from app.models import OptimizationFinding
from app.savings_aggregation import aggregate_findings_savings, classify_engine_finding, action_class_label

router = APIRouter(prefix="/idle-resources", tags=["Idle Resources"])

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _normalize(sub: str) -> str:
    return (sub or "").strip().lower()


def _load_idle_findings(
    db: Session,
    subscription_id: str,
    *,
    include_resolved: bool = False,
) -> list[OptimizationFinding]:
    sub = _normalize(subscription_id)
    query = db.query(OptimizationFinding).filter(OptimizationFinding.subscription_id == sub)
    if not include_resolved:
        query = query.filter(OptimizationFinding.status.in_(sorted(OPEN_IDLE_STATUSES)))
    return query.order_by(OptimizationFinding.estimated_savings_usd.desc()).all()


def _serialize_idle_finding(
    f: OptimizationFinding,
    *,
    savings_usd: float,
    savings_source: str,
) -> dict[str, Any]:
    action_class = classify_engine_finding(f).value
    return {
        "finding_id": f.id,
        "rule_id": f.rule_id,
        "resource_id": f.resource_id,
        "resource_name": f.resource_name,
        "resource_type": f.resource_type,
        "resource_group": f.resource_group,
        "location": f.location,
        "category": heatmap_category(category=f.category, resource_type=f.resource_type),
        "action_class": action_class,
        "action_class_label": action_class_label(action_class),
        "title": f.rule_name or f.rule_id or "Idle resource",
        "detail": f.detail,
        "recommendation": f.recommendation,
        "severity": normalize_severity(f.severity),
        "status": f.status,
        "estimated_savings_usd": round(savings_usd, 2),
        "savings_source": savings_source,
    }


def _empty_matrix_cell() -> dict[str, int | float]:
    return {"count": 0, "savings_usd": 0.0}


def _matrix_key(category: str, severity: str) -> str:
    return f"{category}|{severity}"


def _resolve_savings_map(
    findings: list[OptimizationFinding],
    db: Session,
    subscription_id: str,
) -> dict[str, tuple[float, str]]:
    resource_ids = {
        normalize_arm_id(f.resource_id)
        for f in findings
        if getattr(f, "resource_id", None)
    }
    cost_map = load_resource_costs_usd(db, subscription_id, resource_ids)
    resolved: dict[str, tuple[float, str]] = {}
    for f in findings:
        rid = normalize_arm_id(f.resource_id)
        savings, source = resolve_finding_savings_usd(
            f,
            resource_cost_usd=cost_map.get(rid),
        )
        resolved[f.id] = (savings, source)
    return resolved


def _savings_breakdown(resolved: dict[str, tuple[float, str]]) -> dict[str, int]:
    counts = {"stored": 0, "evidence": 0, "evidence_cost": 0, "resource_cost": 0, "none": 0}
    for _savings, source in resolved.values():
        counts[source] = counts.get(source, 0) + 1
    return counts


@router.get("/sweep/{subscription_id}")
def idle_resource_sweep(
    subscription_id: str,
    severity: str | None = Query(None, description="Filter by severity: critical, high, medium, low"),
    category: str | None = Query(None, description="Filter by resource category"),
    include_resolved: bool = Query(False, description="Include resolved findings"),
    limit: int = Query(2000, ge=1, le=5000, description="Max findings returned in idle_resources"),
    db: Session = Depends(get_db),
) -> dict:
    """Sweep all resource types for idle / orphaned / stale resources using stored findings."""
    findings = [
        f for f in _load_idle_findings(db, subscription_id, include_resolved=include_resolved)
        if is_idle_or_waste_rule(f.rule_id)
    ]
    savings_map = _resolve_savings_map(findings, db, subscription_id)

    items: list[dict] = []
    category_counts: dict[str, int] = {}
    category_savings: dict[str, float] = {}
    severity_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    heatmap_matrix: dict[str, dict[str, int | float]] = {}
    total_savings_usd = 0.0
    findings_with_savings = 0

    severity_filter = severity.lower() if severity else None
    category_filter = category.lower() if category else None

    for f in findings:
        savings, source = savings_map[f.id]
        item = _serialize_idle_finding(f, savings_usd=savings, savings_source=source)
        if severity_filter and item["severity"] != severity_filter:
            continue
        if category_filter and item["category"].lower() != category_filter:
            continue

        cat = item["category"]
        sev = item["severity"]

        category_counts[cat] = category_counts.get(cat, 0) + 1
        category_savings[cat] = round(category_savings.get(cat, 0.0) + savings, 2)
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        total_savings_usd += savings
        if savings > 0:
            findings_with_savings += 1

        cell_key = _matrix_key(cat, sev)
        cell = heatmap_matrix.setdefault(cell_key, _empty_matrix_cell())
        cell["count"] = int(cell["count"]) + 1
        cell["savings_usd"] = round(float(cell["savings_usd"]) + savings, 2)

        items.append(item)

    items.sort(
        key=lambda x: (
            _SEVERITY_ORDER.get(x["severity"], 4),
            -x["estimated_savings_usd"],
        )
    )

    page = items[:limit]
    savings_rollup = aggregate_findings_savings(findings, savings_map)
    return {
        "subscription_id": subscription_id,
        "total_idle_findings": len(items),
        "total_estimated_savings_usd": savings_rollup["total_estimated_savings_usd"],
        "raw_total_estimated_savings_usd": savings_rollup["raw_total_estimated_savings_usd"],
        "double_count_avoided_usd": savings_rollup["double_count_avoided_usd"],
        "by_action_class_savings": savings_rollup["by_action_class_savings"],
        "findings_with_savings": savings_rollup["findings_with_savings"],
        "savings_breakdown": _savings_breakdown(savings_map),
        "by_severity": severity_counts,
        "by_category": category_counts,
        "by_category_savings": category_savings,
        "heatmap_matrix": heatmap_matrix,
        "idle_resources": page,
        "items_returned": len(page),
        "items_truncated": len(page) < len(items),
        "source": "database",
    }


@router.get("/summary/{subscription_id}")
def idle_resource_summary(
    subscription_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """High-level summary of idle resources — counts and total potential savings."""
    findings = [
        f for f in _load_idle_findings(db, subscription_id, include_resolved=False)
        if is_idle_or_waste_rule(f.rule_id)
    ]
    savings_map = _resolve_savings_map(findings, db, subscription_id)

    total_savings = 0.0
    findings_with_savings = 0
    by_rule: dict[str, dict] = {}
    for f in findings:
        savings, _source = savings_map[f.id]
        total_savings += savings
        if savings > 0:
            findings_with_savings += 1
        key = f.rule_id or "UNKNOWN"
        title = f.rule_name or key
        entry = by_rule.setdefault(key, {"rule_id": key, "count": 0, "savings_usd": 0.0, "title": title})
        entry["count"] += 1
        entry["savings_usd"] = round(entry["savings_usd"] + savings, 2)

    rule_summary = sorted(by_rule.values(), key=lambda x: (-x["savings_usd"], -x["count"]))
    most_common = max(by_rule.values(), key=lambda x: x["count"]) if by_rule else None
    savings_rollup = aggregate_findings_savings(findings, savings_map)
    return {
        "subscription_id": subscription_id,
        "total_idle_findings": len(findings),
        "total_estimated_savings_usd": savings_rollup["total_estimated_savings_usd"],
        "raw_total_estimated_savings_usd": savings_rollup["raw_total_estimated_savings_usd"],
        "double_count_avoided_usd": savings_rollup["double_count_avoided_usd"],
        "by_action_class_savings": savings_rollup["by_action_class_savings"],
        "findings_with_savings": savings_rollup["findings_with_savings"],
        "savings_breakdown": _savings_breakdown(savings_map),
        "top_rules": rule_summary[:20],
        "most_common_rule": most_common,
        "source": "database",
    }
