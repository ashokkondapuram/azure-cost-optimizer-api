"""Savings planner — baseline spend and commitment scenario modelling."""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.azure_reservations import fetch_live_commitments
from app.cost_live_query import query_cost_by_service_live
from app.models import AdvisorRecommendation, CostDailyByServiceSnapshot, OptimizationFinding
from app.reservation_advisor_core import _advisor_recommendation, _is_reservation_advisor_row
from app.resource_pricing import RESERVED_INSTANCE_DISCOUNTS, SAVINGS_PLAN_DISCOUNTS

log = structlog.get_logger()

_COMMITMENT_RULES = frozenset({
    "RESERVED_OPPORTUNITY",
    "RESERVED_OPPORTUNITY_EXTENDED",
    "VM_COMMITMENT_CANDIDATE",
    "VM_NO_RESERVED",
    "SAVINGS_PLAN_OPPORTUNITY",
    "SAVINGS_PLAN_OPPORTUNITY_EXTENDED",
})

_CATEGORY_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"virtual machine|compute", re.I), "vms", "Virtual machines"),
    (re.compile(r"kubernetes|container", re.I), "aks", "AKS clusters"),
    (re.compile(r"sql|database", re.I), "sql", "SQL databases"),
    (re.compile(r"storage", re.I), "storage", "Storage accounts"),
    (re.compile(r"app service|web sites|functions", re.I), "appsvcs", "App services"),
]

_PLAN_DEFS = [
    ("payg", "Pay-as-you-go", 1.0, 0, 0, "none"),
    ("savings_plan_1yr", "1-year savings plan", 1.0 - SAVINGS_PLAN_DISCOUNTS["1yr"], int(SAVINGS_PLAN_DISCOUNTS["1yr"] * 100), 1, "savings_plan"),
    ("savings_plan_3yr", "3-year savings plan", 1.0 - SAVINGS_PLAN_DISCOUNTS["3yr"], int(SAVINGS_PLAN_DISCOUNTS["3yr"] * 100), 3, "savings_plan"),
    ("reserved_instance_1yr", "1-year reserved instances", 1.0 - RESERVED_INSTANCE_DISCOUNTS["1yr"], int(RESERVED_INSTANCE_DISCOUNTS["1yr"] * 100), 1, "reserved_instance"),
    ("reserved_instance_3yr", "3-year reserved instances", 1.0 - RESERVED_INSTANCE_DISCOUNTS["3yr"], int(RESERVED_INSTANCE_DISCOUNTS["3yr"] * 100), 3, "reserved_instance"),
]

_PLAN_ID_BY_COMMITMENT = {
    ("savings_plan", 1): "savings_plan_1yr",
    ("savings_plan", 3): "savings_plan_3yr",
    ("reserved_instance", 1): "reserved_instance_1yr",
    ("reserved_instance", 3): "reserved_instance_3yr",
}


def _categorize_service(service_name: str) -> tuple[str, str]:
    for pattern, cat_id, label in _CATEGORY_PATTERNS:
        if pattern.search(service_name or ""):
            return cat_id, label
    return "other", "Other services"


def _build_categories(
    service_rows: list[tuple[str, float, str]],
) -> tuple[dict[str, dict[str, Any]], str]:
    categories: dict[str, dict[str, Any]] = {}
    currency = "CAD"
    for service_name, amount, row_currency in service_rows:
        cat_id, label = _categorize_service(service_name)
        currency = row_currency or currency
        bucket = categories.setdefault(cat_id, {
            "id": cat_id,
            "label": label,
            "monthly_cost": 0.0,
            "services": [],
        })
        bucket["monthly_cost"] += amount
        bucket["services"].append({
            "service_name": service_name,
            "monthly_cost": round(amount, 2),
        })

    for bucket in categories.values():
        bucket["monthly_cost"] = round(bucket["monthly_cost"], 2)
        bucket["services"].sort(key=lambda s: -s["monthly_cost"])

    return categories, currency


def _baseline_from_db(
    db: Session,
    sub: str,
    start: date,
    end: date,
) -> tuple[dict[str, dict[str, Any]], str, bool]:
    rows = (
        db.query(
            CostDailyByServiceSnapshot.service_name,
            func.sum(CostDailyByServiceSnapshot.cost_billing).label("total"),
            func.max(CostDailyByServiceSnapshot.billing_currency).label("currency"),
        )
        .filter(
            CostDailyByServiceSnapshot.subscription_id == sub,
            CostDailyByServiceSnapshot.cost_date >= start.isoformat(),
            CostDailyByServiceSnapshot.cost_date <= end.isoformat(),
            CostDailyByServiceSnapshot.service_name != "__subscription__",
        )
        .group_by(CostDailyByServiceSnapshot.service_name)
        .all()
    )
    service_rows = [
        (row.service_name, float(row.total or 0), row.currency or "CAD")
        for row in rows
    ]
    categories, currency = _build_categories(service_rows)
    return categories, currency, bool(rows)


def _baseline_from_azure_live(
    db: Session,
    sub: str,
    start: date,
    end: date,
    *,
    token: str | None = None,
) -> tuple[dict[str, dict[str, Any]], str, bool]:
    live = query_cost_by_service_live(
        db,
        sub,
        "Custom",
        from_date=start.isoformat(),
        to_date=end.isoformat(),
        token=token,
    )
    if not live:
        return {}, "CAD", False

    props = live.get("properties") or {}
    rows = props.get("rows") or []
    service_rows: list[tuple[str, float, str]] = []
    currency = str(live.get("billing_currency") or "CAD")
    for row in rows:
        if not row or len(row) < 2:
            continue
        service_name = str(row[0] or "Unknown")
        amount = float(row[1] or 0)
        row_currency = str(row[3] if len(row) > 3 else currency)
        service_rows.append((service_name, amount, row_currency))

    categories, currency = _build_categories(service_rows)
    return categories, currency, bool(service_rows)


def _plan_rows(
    monthly_baseline: float,
    *,
    azure_savings: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    azure_savings = azure_savings or {}
    for key, label, multiplier, discount_pct, years, commitment_type in _PLAN_DEFS:
        monthly = round(monthly_baseline * multiplier, 2)
        monthly_saving = round(monthly_baseline - monthly, 2)
        azure_monthly = azure_savings.get(key)
        if azure_monthly is not None and azure_monthly > monthly_saving:
            monthly_saving = round(azure_monthly, 2)
            monthly = round(max(0.0, monthly_baseline - monthly_saving), 2)
        annual = round(monthly * 12, 2)
        term_months = years * 12 if years else 12
        total_saving = round(monthly_saving * term_months, 2) if years else 0.0
        rows.append({
            "id": key,
            "label": label,
            "commitment_type": commitment_type,
            "discount_pct": discount_pct,
            "years": years,
            "monthly_cost": monthly,
            "monthly_saving": monthly_saving,
            "annual_cost": annual,
            "total_saving": total_saving,
            "multiplier": multiplier,
            "azure_backed_saving": round(azure_monthly, 2) if azure_monthly else None,
            "data_source": "azure" if azure_monthly else "estimate",
        })
    return rows


def _azure_savings_by_plan(
    advisor_recs: list[dict[str, Any]],
    capacity_recs: list[dict[str, Any]],
) -> dict[str, float]:
    savings: dict[str, float] = {}
    for rec in advisor_recs:
        plan_id = _PLAN_ID_BY_COMMITMENT.get(
            (rec.get("commitment_type"), 1 if "3" not in str(rec.get("title", "")).lower() else 3),
        )
        if rec.get("commitment_type") == "savings_plan":
            amount = float(rec.get("estimated_monthly_savings") or 0)
            savings["savings_plan_1yr"] = max(savings.get("savings_plan_1yr", 0), amount)
            savings["savings_plan_3yr"] = max(savings.get("savings_plan_3yr", 0), amount * 1.15)
        elif plan_id:
            savings[plan_id] = max(savings.get(plan_id, 0), float(rec.get("estimated_monthly_savings") or 0))

    for rec in capacity_recs:
        plan_id = rec.get("plan_id")
        if not plan_id:
            continue
        savings[plan_id] = max(savings.get(plan_id, 0), float(rec.get("monthly_saving") or 0))

    return savings


def _pick_recommended_plan(plans: list[dict[str, Any]]) -> str:
    candidates = [p for p in plans if p["id"] != "payg"]
    if not candidates:
        return "savings_plan_1yr"
    azure_backed = [p for p in candidates if p.get("azure_backed_saving")]
    pool = azure_backed or candidates
    best = max(pool, key=lambda p: p["monthly_saving"])
    return best["id"]


def build_savings_estimate(
    db: Session,
    subscription_id: str,
    *,
    lookback_days: int = 30,
    selected_categories: list[str] | None = None,
    headers: dict[str, str] | None = None,
    include_live_azure: bool = True,
    token: str | None = None,
) -> dict[str, Any]:
    """Build savings planner estimate from live Azure cost + commitments, with DB fallback."""
    sub = subscription_id.strip().lower()
    end = date.today()
    start = end - timedelta(days=max(lookback_days, 1))
    warnings: list[str] = []
    sources: dict[str, Any] = {
        "cost_baseline": "empty",
        "azure_inventory": False,
        "azure_advisor_db": False,
        "azure_reservation_recommendations": False,
        "engine_findings": True,
    }

    categories: dict[str, dict[str, Any]] = {}
    currency = "CAD"
    has_cost = False

    if include_live_azure and (headers or token):
        try:
            categories, currency, has_cost = _baseline_from_azure_live(
                db, sub, start, end, token=token,
            )
            if has_cost:
                sources["cost_baseline"] = "azure_live"
        except Exception as exc:
            warnings.append(f"Azure live cost query: {str(exc)[:120]}")
            log.warning("savings_planner.live_cost_failed", subscription_id=sub, error=str(exc)[:200])

    if not has_cost:
        categories, currency, has_cost = _baseline_from_db(db, sub, start, end)
        if has_cost:
            sources["cost_baseline"] = "database"

    service_list = sorted(categories.values(), key=lambda c: -c["monthly_cost"])

    if selected_categories:
        selected = {c.lower() for c in selected_categories if c}
        service_list = [c for c in service_list if c["id"] in selected]

    monthly_baseline = round(sum(c["monthly_cost"] for c in service_list), 2)

    advisor_recs: list[dict[str, Any]] = []
    advisor_rows = (
        db.query(AdvisorRecommendation)
        .filter(
            AdvisorRecommendation.subscription_id == sub,
            AdvisorRecommendation.status == "Active",
        )
        .all()
    )
    advisor_recs = [_advisor_recommendation(r) for r in advisor_rows if _is_reservation_advisor_row(r)]
    sources["azure_advisor_db"] = bool(advisor_recs)

    live_commitments: dict[str, Any] = {
        "reservations": [],
        "savings_plans": [],
        "reservation_recommendations": [],
    }
    capacity_recs: list[dict[str, Any]] = []
    if include_live_azure and headers:
        try:
            live_commitments = fetch_live_commitments(sub, headers)
            sources["azure_inventory"] = bool(
                live_commitments.get("reservations") or live_commitments.get("savings_plans")
            )
            capacity_recs = live_commitments.get("reservation_recommendations") or []
            sources["azure_reservation_recommendations"] = bool(capacity_recs)
        except Exception as exc:
            warnings.append(f"Azure inventory: {str(exc)[:120]}")
            log.warning("savings_planner.live_inventory_failed", subscription_id=sub, error=str(exc)[:200])
    elif include_live_azure:
        warnings.append("Azure live data skipped — no ARM credentials in this request.")

    azure_savings = _azure_savings_by_plan(advisor_recs, capacity_recs)
    plans = _plan_rows(monthly_baseline, azure_savings=azure_savings)

    findings = (
        db.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == sub,
            OptimizationFinding.status.in_(["open", "acknowledged"]),
            OptimizationFinding.rule_id.in_(list(_COMMITMENT_RULES)),
        )
        .order_by(OptimizationFinding.estimated_savings_usd.desc())
        .limit(25)
        .all()
    )
    opportunities = [{
        "finding_id": f.id,
        "rule_id": f.rule_id,
        "title": f.title,
        "resource_id": f.resource_id,
        "severity": f.severity,
        "estimated_savings_monthly": round(float(f.estimated_savings_usd or 0), 2),
    } for f in findings]

    active_commitments = [
        *live_commitments.get("reservations", []),
        *live_commitments.get("savings_plans", []),
    ]

    advisor_opportunity_monthly = round(
        sum(r.get("estimated_monthly_savings") or 0 for r in advisor_recs), 2,
    )
    capacity_opportunity_monthly = round(
        sum(r.get("monthly_saving") or 0 for r in capacity_recs), 2,
    )

    if not has_cost:
        warnings.append("No cost data found. Sync costs from Azure or run a cost sync.")
    if include_live_azure and not sources["azure_inventory"] and not warnings:
        warnings.append("No active reservations or savings plans returned from Azure.")

    message = None
    if not has_cost:
        message = "No cost data found. Sync from Azure or run a cost sync first."

    return {
        "subscription_id": sub,
        "lookback_days": lookback_days,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "billing_currency": currency,
        "monthly_baseline": monthly_baseline,
        "categories": service_list,
        "all_categories": sorted(categories.values(), key=lambda c: -c["monthly_cost"]),
        "plans": plans,
        "recommended_plan_id": _pick_recommended_plan(plans),
        "commitment_opportunities": opportunities,
        "opportunity_savings_monthly": round(sum(o["estimated_savings_monthly"] for o in opportunities), 2),
        "advisor_recommendations": advisor_recs[:25],
        "azure_reservation_recommendations": capacity_recs[:25],
        "advisor_opportunity_monthly": advisor_opportunity_monthly,
        "azure_capacity_opportunity_monthly": capacity_opportunity_monthly,
        "active_commitments": active_commitments,
        "sources": sources,
        "warnings": warnings,
        "source": sources["cost_baseline"],
        "message": message,
    }


def sync_savings_planner(
    db: Session,
    subscription_id: str,
    token: str,
    *,
    lookback_days: int = 30,
    selected_categories: list[str] | None = None,
    trigger_advisor_generate: bool = False,
) -> dict[str, Any]:
    """Refresh Advisor snapshots and return savings estimate with live Azure data."""
    from app.advisor_sync import sync_azure_advisor_recommendations
    from app.auth import arm_auth_context

    sub = subscription_id.strip().lower()
    advisor_result: dict[str, Any] = {"status": "skipped"}
    with arm_auth_context(db=db, token=token):
        try:
            advisor_result = sync_azure_advisor_recommendations(
                sub,
                db,
                token,
                trigger_generate=trigger_advisor_generate,
                wait_for_generate=False,
            )
        except Exception as exc:
            advisor_result = {"status": "error", "error": str(exc)[:200]}
            log.warning("savings_planner.advisor_sync_failed", error=str(exc)[:200])

        payload = build_savings_estimate(
            db,
            sub,
            lookback_days=lookback_days,
            selected_categories=selected_categories,
            headers={"Authorization": f"Bearer {token}"},
            include_live_azure=True,
            token=token,
        )

    payload["sync"] = {
        "advisor": advisor_result,
        "status": "ok" if advisor_result.get("status") in {"ok", "partial", "skipped"} else "error",
    }
    return payload
