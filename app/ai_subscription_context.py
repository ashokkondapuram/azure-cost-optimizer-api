"""Extra subscription context for AI recommendations — fills common data gaps."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.analysis_persist import dedupe_open_findings_for_display
from app.cost_db import month_for_timeframe
from app.models import CostByResourceSnapshot, CostByResourceTypeSnapshot, OptimizationFinding

_NETWORK_SERVICE_PATTERN = re.compile(
    r"virtual network|load balancer|application gateway|bandwidth|"
    r"firewall|front door|private link|vpn|expressroute|nat gateway|"
    r"public ip|dns|cdn|traffic manager",
    re.I,
)
_STORAGE_SERVICE_PATTERN = re.compile(r"storage|backup|recovery services", re.I)

_GOVERNANCE_GAP = re.compile(r"governance.*cost|impact.*governance", re.I)
_CATEGORY_GAP = re.compile(
    r"network.*storage|storage.*network|detailed cost analysis.*(network|storage)",
    re.I,
)


def _normalize_sub(subscription_id: str) -> str:
    return subscription_id.strip().lower()


def _cost_month(db: Session, subscription_id: str) -> str:
    sub = _normalize_sub(subscription_id)
    month = month_for_timeframe("MonthToDate")
    latest = (
        db.query(func.max(CostByResourceTypeSnapshot.month))
        .filter(CostByResourceTypeSnapshot.subscription_id == sub)
        .scalar()
    )
    return latest or month


def _sum_billing(rows: list) -> float:
    total = 0.0
    for row in rows:
        billing = row.cost_billing if row.cost_billing is not None else row.cost_usd
        total += float(billing or 0)
    return round(total, 2)


def _domain_cost_rows(db: Session, subscription_id: str, month: str, domain: str) -> list:
    sub = _normalize_sub(subscription_id)
    prefix = f"{domain}/"
    return (
        db.query(CostByResourceTypeSnapshot)
        .filter(
            CostByResourceTypeSnapshot.subscription_id == sub,
            CostByResourceTypeSnapshot.month == month,
            CostByResourceTypeSnapshot.canonical_resource_type.isnot(None),
            CostByResourceTypeSnapshot.canonical_resource_type.like(f"{prefix}%"),
        )
        .order_by(CostByResourceTypeSnapshot.cost_billing.desc())
        .all()
    )


def _service_spend_by_pattern(
    db: Session,
    subscription_id: str,
    month: str,
    pattern: re.Pattern[str],
) -> tuple[float, list[dict[str, Any]]]:
    from app.models import CostByServiceSnapshot

    sub = _normalize_sub(subscription_id)
    rows = (
        db.query(CostByServiceSnapshot)
        .filter(
            CostByServiceSnapshot.subscription_id == sub,
            CostByServiceSnapshot.month == month,
            CostByServiceSnapshot.service_name != "__subscription__",
        )
        .all()
    )
    matched: list[dict[str, Any]] = []
    total = 0.0
    currency = "CAD"
    for row in rows:
        name = row.service_name or ""
        if not pattern.search(name):
            continue
        currency = row.billing_currency or currency
        amount = float(row.cost_billing or row.cost_usd or 0)
        total += amount
        matched.append({
            "service_name": name,
            "mtd_spend": round(amount, 2),
            "currency": row.billing_currency or currency,
        })
    matched.sort(key=lambda item: item["mtd_spend"], reverse=True)
    return round(total, 2), matched


def _resource_cost_lookup(
    db: Session,
    subscription_id: str,
    month: str,
    resource_ids: set[str],
) -> float:
    if not resource_ids:
        return 0.0
    sub = _normalize_sub(subscription_id)
    lowered = {rid.lower() for rid in resource_ids if rid}
    rows = (
        db.query(CostByResourceSnapshot)
        .filter(
            CostByResourceSnapshot.subscription_id == sub,
            CostByResourceSnapshot.month == month,
        )
        .all()
    )
    total = 0.0
    for row in rows:
        rid = (row.resource_id or "").lower()
        if rid not in lowered:
            continue
        total += float(row.cost_billing if row.cost_billing is not None else row.cost_usd or 0)
    return round(total, 2)


def _open_findings(db: Session, subscription_id: str) -> list[OptimizationFinding]:
    sub = _normalize_sub(subscription_id)
    rows = (
        db.query(OptimizationFinding)
        .filter(
            func.lower(OptimizationFinding.subscription_id) == sub,
            OptimizationFinding.status.in_(["open", "acknowledged"]),
        )
        .all()
    )
    return dedupe_open_findings_for_display(rows)


def build_governance_impact(
    db: Session,
    subscription_id: str,
    *,
    mtd_pretax: float | None,
    billing_currency: str,
    month: str,
) -> dict[str, Any]:
    """Quantify how governance findings relate to subscription spend."""
    from app.tag_compliance_core import compute_tag_compliance

    findings = _open_findings(db, subscription_id)
    governance = [
        f for f in findings
        if str(f.category or "").strip().upper() == "GOVERNANCE"
    ]
    resource_ids = {f.resource_id for f in governance if f.resource_id}
    affected_spend = _resource_cost_lookup(db, subscription_id, month, resource_ids)

    tag = compute_tag_compliance(db, subscription_id, limit=5000)
    non_compliant_ids = {
        item.get("resource_id")
        for item in (tag.get("non_compliant_resources") or [])
        if item.get("resource_id")
    }
    non_compliant_spend = _resource_cost_lookup(db, subscription_id, month, non_compliant_ids)

    savings = round(sum(float(f.estimated_savings_usd or 0) for f in governance), 2)
    by_rule = Counter(str(f.rule_id or "unknown") for f in governance)
    mtd = float(mtd_pretax or 0)
    pct_affected = round(100 * affected_spend / mtd, 1) if mtd > 0 and affected_spend > 0 else None
    pct_non_compliant = round(100 * non_compliant_spend / mtd, 1) if mtd > 0 and non_compliant_spend > 0 else None

    payload: dict[str, Any] = {
        "available": bool(governance or tag.get("total_resources")),
        "billing_currency": billing_currency,
        "month": month,
        "open_governance_findings": len(governance),
        "governance_estimated_monthly_savings_usd": savings,
        "top_governance_rules": [
            {"rule_id": rule_id, "count": count}
            for rule_id, count in by_rule.most_common(5)
        ],
        "tag_compliance_score_pct": tag.get("score_pct"),
        "non_compliant_resources": int(tag.get("non_compliant_count") or 0),
        "total_tagged_resources": int(tag.get("total_resources") or 0),
        "mtd_spend_on_governance_flagged_resources": affected_spend,
        "mtd_spend_on_non_compliant_resources": non_compliant_spend,
        "pct_subscription_mtd_on_governance_flagged_resources": pct_affected,
        "pct_subscription_mtd_on_non_compliant_resources": pct_non_compliant,
    }
    if mtd > 0:
        payload["subscription_mtd_pretax"] = round(mtd, 2)
    return payload


def build_category_cost_analysis(
    db: Session,
    subscription_id: str,
    *,
    domain: str,
    service_pattern: re.Pattern[str],
    findings: list[OptimizationFinding],
    mtd_pretax: float | None,
    billing_currency: str,
    month: str,
) -> dict[str, Any]:
    """Detailed MTD cost and finding summary for a spend domain (network or storage)."""
    rows = _domain_cost_rows(db, subscription_id, month, domain)
    domain_spend = _sum_billing(rows)
    service_spend, services = _service_spend_by_pattern(db, subscription_id, month, service_pattern)

    domain_findings = [
        f for f in findings
        if str(f.category or "").strip().lower() == domain
        or (f.resource_type or "").lower().startswith(f"microsoft.{domain}")
    ]

    finding_savings = round(sum(float(f.estimated_savings_usd or 0) for f in domain_findings), 2)
    by_rule = Counter(str(f.rule_id or "unknown") for f in domain_findings)
    mtd = float(mtd_pretax or 0)

    top_types = [
        {
            "arm_resource_type": row.arm_resource_type,
            "canonical_resource_type": row.canonical_resource_type,
            "mtd_spend": round(float(row.cost_billing if row.cost_billing is not None else row.cost_usd or 0), 2),
        }
        for row in rows[:8]
    ]

    return {
        "available": bool(rows or services or domain_findings),
        "domain": domain,
        "billing_currency": billing_currency,
        "month": month,
        "mtd_spend_by_resource_type": domain_spend,
        "mtd_spend_by_service": service_spend,
        "pct_of_subscription_mtd": round(100 * domain_spend / mtd, 1) if mtd > 0 and domain_spend > 0 else None,
        "top_resource_types": top_types,
        "top_services": services[:8],
        "open_findings_count": len(domain_findings),
        "estimated_monthly_savings_usd": finding_savings,
        "top_finding_rules": [
            {"rule_id": rule_id, "count": count}
            for rule_id, count in by_rule.most_common(5)
        ],
    }


def enrich_subscription_context(
    db: Session,
    subscription_id: str,
    base_context: dict[str, Any],
) -> dict[str, Any]:
    """Attach governance impact and network/storage cost analysis to AI context."""
    sub = _normalize_sub(subscription_id)
    month = _cost_month(db, sub)
    mtd = base_context.get("mtd_spend") or {}
    mtd_pretax = mtd.get("pretax_total")
    billing_currency = mtd.get("billing_currency") or "CAD"

    findings = _open_findings(db, sub)
    governance_impact = build_governance_impact(
        db,
        sub,
        mtd_pretax=mtd_pretax,
        billing_currency=billing_currency,
        month=month,
    )
    network_cost_analysis = build_category_cost_analysis(
        db,
        sub,
        domain="network",
        service_pattern=_NETWORK_SERVICE_PATTERN,
        findings=findings,
        mtd_pretax=mtd_pretax,
        billing_currency=billing_currency,
        month=month,
    )
    storage_cost_analysis = build_category_cost_analysis(
        db,
        sub,
        domain="storage",
        service_pattern=_STORAGE_SERVICE_PATTERN,
        findings=findings,
        mtd_pretax=mtd_pretax,
        billing_currency=billing_currency,
        month=month,
    )

    enriched = dict(base_context)
    enriched["cost_month"] = month
    enriched["governance_impact"] = governance_impact
    enriched["network_cost_analysis"] = network_cost_analysis
    enriched["storage_cost_analysis"] = storage_cost_analysis
    return enriched


def filter_resolved_data_gaps(
    data_gaps: list[str],
    context: dict[str, Any],
) -> list[str]:
    """Drop AI-flagged gaps that enriched context already covers."""
    governance = context.get("governance_impact") or {}
    network = context.get("network_cost_analysis") or {}
    storage = context.get("storage_cost_analysis") or {}
    governance_ready = bool(
        governance.get("available")
        and (
            governance.get("open_governance_findings")
            or governance.get("tag_compliance_score_pct") is not None
        )
    )
    category_ready = bool(
        (network.get("available") and network.get("mtd_spend_by_resource_type") is not None)
        and (storage.get("available") and storage.get("mtd_spend_by_resource_type") is not None)
    )

    kept: list[str] = []
    for gap in data_gaps:
        text = str(gap or "").strip()
        if not text:
            continue
        if governance_ready and _GOVERNANCE_GAP.search(text):
            continue
        if category_ready and _CATEGORY_GAP.search(text):
            continue
        kept.append(text)
    return kept
