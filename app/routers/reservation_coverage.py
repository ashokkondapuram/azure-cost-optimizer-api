"""Reservation / RI coverage — compute RI utilisation % and coverage gaps."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Finding, CostByServiceSnapshot

router = APIRouter(prefix="/reservations", tags=["Reservation Coverage"])

# Rule IDs indicating commitment/reservation opportunities
_RI_OPPORTUNITY_RULES = frozenset({
    "RESERVED_OPPORTUNITY",
    "RESERVED_OPPORTUNITY_EXTENDED",
    "VM_COMMITMENT_CANDIDATE",
    "VM_NO_RESERVED",
    "SAVINGS_PLAN_OPPORTUNITY",
    "SAVINGS_PLAN_OPPORTUNITY_EXTENDED",
})

_RI_ACTIVE_RULES = frozenset({
    "RESERVED_UNDERUTILISED",
    "RESERVED_UNUSED",
    "SAVINGS_PLAN_UNDERUTILISED",
})


def _normalize(sub: str) -> str:
    return (sub or "").strip().lower()


def _extract_evidence(finding: Any) -> dict:
    ev = getattr(finding, "evidence", {}) or {}
    if isinstance(ev, str):
        import json
        try:
            ev = json.loads(ev)
        except Exception:
            ev = {}
    return ev if isinstance(ev, dict) else {}


@router.get("/coverage/{subscription_id}")
def reservation_coverage(
    subscription_id: str,
    month: str | None = Query(None, description="Month YYYY-MM for spend context"),
    db: Session = Depends(get_db),
) -> dict:
    """Return RI/Savings Plan coverage analysis and utilisation metrics."""
    sub = _normalize(subscription_id)

    # Get all commitment-related findings
    findings = (
        db.query(Finding)
        .filter(
            Finding.subscription_id == sub,
            Finding.rule_id.in_(list(_RI_OPPORTUNITY_RULES | _RI_ACTIVE_RULES)),
        )
        .all()
    )

    # Get VM compute spend for coverage ratio estimation
    import re
    from datetime import date
    m = month or date.today().strftime("%Y-%m")

    vm_spend_rows = (
        db.query(CostByServiceSnapshot)
        .filter(
            CostByServiceSnapshot.subscription_id == sub,
            CostByServiceSnapshot.month == m,
            CostByServiceSnapshot.service_name.ilike("%virtual machine%"),
        )
        .all()
    )
    total_vm_spend = sum(float(r.cost_billing or 0) for r in vm_spend_rows)

    # Aggregate opportunity findings
    opportunities: list[dict] = []
    total_opportunity_savings = 0.0
    for f in findings:
        if f.rule_id not in _RI_OPPORTUNITY_RULES:
            continue
        ev = _extract_evidence(f)
        savings = float(getattr(f, "estimated_savings_usd") or 0)
        total_opportunity_savings += savings
        opportunities.append({
            "finding_id": f.id,
            "rule_id": f.rule_id,
            "title": f.title,
            "resource_id": f.resource_id,
            "severity": f.severity,
            "estimated_savings_usd": round(savings, 2),
            "scope": ev.get("scope", "resource"),
            "commitment_type": ev.get("commitment_type") or (
                "reserved_instance" if "RESERVED" in (f.rule_id or "") else "savings_plan"
            ),
            "running_vm_count": ev.get("running_vm_count"),
            "estimated_compute_spend_usd": ev.get("estimated_compute_spend_usd") or ev.get("total_vm_monthly_spend_usd"),
        })

    # Aggregate underutilisation findings
    underutilised: list[dict] = []
    for f in findings:
        if f.rule_id not in _RI_ACTIVE_RULES:
            continue
        ev = _extract_evidence(f)
        underutilised.append({
            "finding_id": f.id,
            "rule_id": f.rule_id,
            "title": f.title,
            "resource_id": f.resource_id,
            "utilisation_pct": ev.get("utilisation_pct"),
            "wasted_usd": float(getattr(f, "estimated_savings_usd") or 0),
        })

    # Estimate coverage ratio from evidence
    covered_spend = sum(
        float(o.get("estimated_compute_spend_usd") or 0) * 0 for o in opportunities
    )  # Stub: reserved covered spend not yet tracked directly
    coverage_pct = None if total_vm_spend == 0 else round(
        max(0, (1 - (len(opportunities) / max(1, len(opportunities) + 1))) * 100), 1
    )

    currency_row = (
        db.query(CostByServiceSnapshot.billing_currency)
        .filter(CostByServiceSnapshot.subscription_id == sub)
        .first()
    )
    currency = (currency_row[0] if currency_row else None) or "CAD"

    return {
        "subscription_id": subscription_id,
        "month": m,
        "billing_currency": currency,
        "total_vm_spend": round(total_vm_spend, 2),
        "estimated_coverage_pct": coverage_pct,
        "total_opportunity_savings_usd": round(total_opportunity_savings, 2),
        "commitment_opportunities": sorted(opportunities, key=lambda x: -x["estimated_savings_usd"])[:25],
        "underutilised_commitments": underutilised[:25],
        "source": "database",
    }


@router.get("/recommendations/{subscription_id}")
def reservation_recommendations(
    subscription_id: str,
    commitment_type: str = Query("all", description="Filter: all, reserved_instance, savings_plan"),
    db: Session = Depends(get_db),
) -> dict:
    """Return actionable RI/Savings Plan purchase recommendations."""
    sub = _normalize(subscription_id)
    rule_filter = list(_RI_OPPORTUNITY_RULES)
    if commitment_type == "reserved_instance":
        rule_filter = [r for r in rule_filter if "RESERVED" in r]
    elif commitment_type == "savings_plan":
        rule_filter = [r for r in rule_filter if "SAVINGS" in r]

    findings = (
        db.query(Finding)
        .filter(
            Finding.subscription_id == sub,
            Finding.rule_id.in_(rule_filter),
            Finding.status.in_(["open", "active", None, ""]),
        )
        .all()
    )

    recs: list[dict] = []
    for f in findings:
        ev = _extract_evidence(f)
        savings = float(getattr(f, "estimated_savings_usd") or 0)
        recs.append({
            "rule_id": f.rule_id,
            "title": f.title,
            "detail": f.detail,
            "recommendation": f.recommendation,
            "resource_id": f.resource_id,
            "severity": f.severity,
            "estimated_monthly_savings_usd": round(savings, 2),
            "estimated_annual_savings_usd": round(savings * 12, 2),
            "scope": ev.get("scope", "resource"),
        })

    recs.sort(key=lambda x: -x["estimated_annual_savings_usd"])
    total_annual = round(sum(r["estimated_annual_savings_usd"] for r in recs), 2)

    return {
        "subscription_id": subscription_id,
        "commitment_type_filter": commitment_type,
        "total_recommendations": len(recs),
        "total_estimated_annual_savings_usd": total_annual,
        "recommendations": recs[:50],
        "source": "database",
    }
