"""DB-backed dashboard API — serves PostgreSQL inventory/cost/findings (no live Azure at query time)."""

from __future__ import annotations

import json
from datetime import date, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.cost_db import (
    cost_by_resource_from_db,
    cost_summary_from_db,
    daily_cost_response_from_db,
    month_for_timeframe,
)
from app.focus_mapping import normalize_arm_id
from app.models import (
    AnalysisJob,
    BudgetSnapshot,
    CostByResourceSnapshot,
    CostSyncRun,
    OptimizationFinding,
    OptimizationRun,
    ResourceSnapshot,
    SubscriptionCache,
)
from app.resource_store import get_resource_counts, rows_to_list

_UNDERUTIL_RULE_PREFIXES = (
    "VM_IDLE",
    "VM_OVERSIZE",
    "VM_RIGHTSIZE",
    "VM_SKU",
    "DISK_UNATTACHED",
    "DISK_UNUSED",
    "DISK_OVERSIZE",
    "AKS_UNDERUTILIZED",
    "APPGW_UNUSED",
    "LB_NO_BACKEND",
    "IP_UNASSOCIATED",
    "IP_IDLE",
    "NIC_UNATTACHED",
    "STORAGE_NO_LIFECYCLE",
    "SQL_SERVERLESS",
)


def _normalize_sub(subscription_id: str) -> str:
    return (subscription_id or "").strip().lower()


def _iso(dt: Any) -> str | None:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.isoformat()
    return dt.astimezone(timezone.utc).isoformat()


def _staleness_label(synced_at: Any) -> str:
    if synced_at is None:
        return "never"
    now = date.today()
    synced_date = synced_at.date() if hasattr(synced_at, "date") else None
    if synced_date is None:
        return "unknown"
    age_days = (now - synced_date).days
    if age_days <= 0:
        return "fresh"
    if age_days <= 1:
        return "recent"
    if age_days <= 7:
        return "aging"
    return "stale"


def get_findings_summary_db(db: Session, subscription_id: str) -> dict[str, Any]:
    """Aggregated open findings — SQL group-by, no full table scan into Python."""
    sub = _normalize_sub(subscription_id)
    filt = (
        OptimizationFinding.subscription_id == sub,
        OptimizationFinding.status == "open",
    )
    open_count = (
        db.query(func.count(OptimizationFinding.id))
        .filter(*filt)
        .scalar()
        or 0
    )
    total_savings = (
        db.query(func.coalesce(func.sum(OptimizationFinding.estimated_savings_usd), 0.0))
        .filter(*filt)
        .scalar()
        or 0.0
    )
    by_sev = dict(
        db.query(OptimizationFinding.severity, func.count(OptimizationFinding.id))
        .filter(*filt)
        .group_by(OptimizationFinding.severity)
        .all()
    )
    by_cat = dict(
        db.query(OptimizationFinding.category, func.count(OptimizationFinding.id))
        .filter(*filt)
        .group_by(OptimizationFinding.category)
        .all()
    )
    return {
        "open_findings": int(open_count),
        "total_estimated_savings_usd": round(float(total_savings), 2),
        "by_severity": by_sev,
        "by_category": by_cat,
    }


def _compact_daily_cost(
    db: Session,
    subscription_id: str,
    timeframe: str = "MonthToDate",
) -> dict[str, Any]:
    raw = daily_cost_response_from_db(db, subscription_id, timeframe)
    if not raw:
        return {"points": [], "billing_currency": "USD", "source": "database"}
    props = raw.get("properties") or {}
    col_names = [c.get("name") for c in props.get("columns") or []]
    points: list[dict[str, Any]] = []
    for row_vals in props.get("rows") or []:
        entry = dict(zip(col_names, row_vals))
        points.append({
            "date": entry.get("UsageDate"),
            "cost_billing": round(float(entry.get("PreTaxCost") or 0), 2),
            "cost_usd": round(float(entry.get("CostUSD") or 0), 2),
        })
    return {
        "points": points,
        "billing_currency": raw.get("billing_currency", "USD"),
        "source": "database",
    }


def _recent_analysis_runs(
    db: Session,
    subscription_id: str,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    sub = _normalize_sub(subscription_id)
    rows = (
        db.query(OptimizationRun)
        .filter(OptimizationRun.subscription_id == sub)
        .order_by(OptimizationRun.analyzed_at.desc())
        .limit(max(1, min(limit, 20)))
        .all()
    )
    return [
        {
            "id": r.id,
            "analyzed_at": _iso(r.analyzed_at),
            "total_findings": r.total_findings,
            "total_savings_usd": round(r.total_savings_usd or 0.0, 2),
            "engine_version": r.engine_version,
        }
        for r in rows
    ]


_SEV_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}


def _weekly_cost_from_points(points: list[dict[str, Any]]) -> dict[str, Any]:
    if not points:
        return {"amount": 0.0, "delta_pct": None, "days": 0}
    sorted_pts = sorted(points, key=lambda p: p.get("date") or "")
    recent = sorted_pts[-7:]
    prior = sorted_pts[-14:-7] if len(sorted_pts) >= 8 else []
    amount = sum(p.get("cost_billing") or p.get("cost_usd") or 0 for p in recent)
    prior_amount = sum(p.get("cost_billing") or p.get("cost_usd") or 0 for p in prior)
    delta_pct = None
    if prior_amount > 0:
        delta_pct = round(((amount - prior_amount) / prior_amount) * 100, 1)
    return {"amount": round(amount, 2), "delta_pct": delta_pct, "days": len(recent)}


def _resource_health_counts(db: Session, subscription_id: str, total_resources: int) -> dict[str, Any]:
    sub = _normalize_sub(subscription_id)
    rows = (
        db.query(OptimizationFinding.resource_id, OptimizationFinding.severity)
        .filter(
            OptimizationFinding.subscription_id == sub,
            OptimizationFinding.status == "open",
            OptimizationFinding.resource_id.isnot(None),
            OptimizationFinding.resource_id != "",
        )
        .all()
    )
    worst: dict[str, str] = {}
    for rid, severity in rows:
        norm = normalize_arm_id(rid)
        if not norm:
            continue
        prev = worst.get(norm)
        if _SEV_RANK.get(severity or "", 0) > _SEV_RANK.get(prev or "", 0):
            worst[norm] = severity or ""

    critical = sum(1 for s in worst.values() if s == "CRITICAL")
    warning = sum(1 for s in worst.values() if s in ("HIGH", "MEDIUM"))
    affected = len(worst)
    healthy = max(0, total_resources - affected)
    return {
        "healthy": healthy,
        "warning": warning,
        "critical": critical,
        "unknown": max(0, total_resources - healthy - warning - critical),
        "total": total_resources,
    }


def _utilization_by_type(underutil_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for item in underutil_items:
        rtype = item.get("resource_type") or "other"
        label = rtype.split("/")[-1] if "/" in rtype else rtype
        bucket = buckets.setdefault(label, {"type": label, "count": 0, "samples": []})
        bucket["count"] += 1
        util = item.get("peak_cpu")
        if util:
            bucket["samples"].append(str(util))
    out = []
    for label, bucket in sorted(buckets.items(), key=lambda x: -x[1]["count"]):
        out.append({
            "type": label,
            "count": bucket["count"],
            "utilization_label": bucket["samples"][0] if bucket["samples"] else "Low",
        })
    return out[:12]


def _cost_vs_utilization(
    top_spend_items: list[dict[str, Any]],
    underutil_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    util_by_id = {normalize_arm_id(i.get("resource_id", "")): i for i in underutil_items}
    merged: list[dict[str, Any]] = []
    for item in top_spend_items[:10]:
        rid = normalize_arm_id(item.get("resource_id", ""))
        util = util_by_id.get(rid) or {}
        cost = item.get("cost_billing") or item.get("cost_usd") or 0
        merged.append({
            "resource_id": rid,
            "name": item.get("resource_name") or rid.split("/")[-1] if rid else "Resource",
            "cost": round(float(cost), 2),
            "utilization": util.get("peak_cpu") or "—",
            "waste_score": util.get("waste_score"),
        })
    return merged


def _build_portal_section(
    db: Session,
    subscription_id: str,
    *,
    inventory_counts: dict[str, Any],
    daily_points: list[dict[str, Any]],
    billing_currency: str,
    underutil_items: list[dict[str, Any]],
    top_spend_items: list[dict[str, Any]],
    cost_summary: dict[str, Any],
) -> dict[str, Any]:
    """azure_dashboard_portal_0698 — KPI row + six dashboard panels."""
    total_resources = int(inventory_counts.get("inventory_total") or 0)
    health = _resource_health_counts(db, subscription_id, total_resources)
    weekly = _weekly_cost_from_points(daily_points)
    mtd_amount = cost_summary.get("pretax_total") or cost_summary.get("cost_usd_total") or 0

    return {
        "title": "Azure resource dashboard",
        "subtitle": "Weekly snapshot across all resource types — cost, utilization, throttling, latency and health",
        "kpis": [
            {
                "id": "total_resources",
                "label": "Total resources",
                "value": total_resources,
                "tone": "default",
                "sub": f"{inventory_counts.get('cost_resources', 0)} with MTD cost",
            },
            {
                "id": "resources_warning",
                "label": "Resources in warning",
                "value": health["warning"],
                "tone": "warn",
                "sub": "Review recommended" if health["warning"] else "No warnings",
            },
            {
                "id": "resources_critical",
                "label": "Critical resources",
                "value": health["critical"],
                "tone": "danger",
                "sub": "Immediate action needed" if health["critical"] else "None critical",
            },
            {
                "id": "weekly_cost",
                "label": "Weekly cost",
                "value": weekly["amount"],
                "currency": billing_currency,
                "tone": "default",
                "sub": (
                    f"{'↓' if (weekly['delta_pct'] or 0) < 0 else '↑'} {abs(weekly['delta_pct'])}% vs prior week"
                    if weekly["delta_pct"] is not None
                    else f"MTD {round(float(mtd_amount), 2):,.2f} {billing_currency}"
                ),
            },
        ],
        "panels": {
            "daily_cost_trend": {
                "title": "Daily cost trend",
                "description": "Shows daily spend across the week to spot peak days and cost drift.",
                "points": daily_points[-14:],
                "currency": billing_currency,
            },
            "utilization_by_resource": {
                "title": "Utilization % by resource",
                "description": "Compares utilization across resource types to find rightsizing candidates.",
                "items": _utilization_by_type(underutil_items),
            },
            "cost_vs_utilization": {
                "title": "Cost vs utilization",
                "description": "Expensive + underused = waste. Expensive + busy = justified.",
                "items": _cost_vs_utilization(top_spend_items, underutil_items),
            },
            "throttle_events_by_day": {
                "title": "Throttle events by day",
                "description": "Shows which days see the most throttling to tune capacity or spot spikes.",
                "items": [],
                "source": "pending_monitor_sync",
            },
            "latency_by_resource": {
                "title": "Latency by resource",
                "description": "Ranks resource types by average latency to prioritize performance tuning.",
                "items": [],
                "source": "pending_monitor_sync",
            },
            "resource_health_status": {
                "title": "Resource health status",
                "description": "Healthy, warning, critical and unknown resources at a glance.",
                "segments": [
                    {"name": "Healthy", "value": health["healthy"], "key": "healthy"},
                    {"name": "Warning", "value": health["warning"], "key": "warning"},
                    {"name": "Critical", "value": health["critical"], "key": "critical"},
                    {"name": "Unknown", "value": health["unknown"], "key": "unknown"},
                ],
            },
        },
    }


def get_dashboard_overview(
    db: Session,
    subscription_id: str,
    *,
    timeframe: str = "MonthToDate",
    top_spend_limit: int = 8,
    advisor_limit: int = 6,
    underutil_limit: int = 6,
    alerts_limit: int = 8,
    runs_limit: int = 10,
) -> dict[str, Any]:
    """Single PostgreSQL-backed payload for the dashboard (one round trip)."""
    sub = _normalize_sub(subscription_id)
    cost_summary = get_cost_dashboard_summary(db, subscription_id, timeframe) or {}
    daily = _compact_daily_cost(db, subscription_id, timeframe)
    inventory_counts = get_resource_counts(db, subscription_id)
    underutil = list_underutil_outliers(db, subscription_id, limit=underutil_limit)
    top_spend = get_top_spend(
        db, subscription_id, limit=top_spend_limit, timeframe=timeframe,
    )
    billing_currency = (
        daily.get("billing_currency")
        or top_spend.get("billing_currency")
        or cost_summary.get("billing_currency")
        or "USD"
    )
    return {
        "subscription_id": sub,
        "data_source": "postgresql",
        "timeframe": timeframe,
        "sync": get_sync_status(db, subscription_id),
        "portal": _build_portal_section(
            db,
            subscription_id,
            inventory_counts=inventory_counts,
            daily_points=daily.get("points") or [],
            billing_currency=billing_currency,
            underutil_items=underutil.get("items") or [],
            top_spend_items=top_spend.get("items") or [],
            cost_summary=cost_summary,
        ),
        "cost": {
            "summary": cost_summary,
            "daily": daily,
            "top_spend": top_spend,
        },
        "optimization": {
            "summary": get_findings_summary_db(db, subscription_id),
            "recommendations": list_advisor_recommendations(
                db, subscription_id, limit=advisor_limit,
            ),
            "underutil": underutil,
        },
        "monitoring": list_monitor_alert_resources(
            db, subscription_id, limit=alerts_limit,
        ),
        "budgets": list_budgets_from_db(db, subscription_id),
        "inventory": {"counts": inventory_counts},
        "analysis_runs": _recent_analysis_runs(db, subscription_id, limit=runs_limit),
    }


def get_sync_status(db: Session, subscription_id: str) -> dict[str, Any]:
    """Last sync timestamps per data type (inventory, cost, analysis)."""
    sub = _normalize_sub(subscription_id)

    sub_row = (
        db.query(SubscriptionCache)
        .filter(SubscriptionCache.subscription_id == sub)
        .first()
    )

    inv_agg = (
        db.query(
            func.max(ResourceSnapshot.synced_at).label("last_synced"),
            func.count(ResourceSnapshot.id).label("resource_count"),
        )
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
        )
        .one()
    )

    cost_row = (
        db.query(CostSyncRun)
        .filter(CostSyncRun.subscription_id == sub)
        .order_by(CostSyncRun.synced_at.desc())
        .first()
    )

    analysis_row = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.subscription_id == sub)
        .order_by(AnalysisJob.created_at.desc())
        .first()
    )

    open_findings = (
        db.query(func.count(OptimizationFinding.id))
        .filter(
            OptimizationFinding.subscription_id == sub,
            OptimizationFinding.status == "open",
        )
        .scalar()
        or 0
    )

    inv_synced = inv_agg.last_synced
    from app.azure_token_cache import get_token_cache_status
    from app.sync_orchestrator import get_pipeline_status

    pipeline = get_pipeline_status(sub)

    return {
        "subscription_id": sub,
        "data_source": "postgresql",
        "pipeline": pipeline,
        "inventory": {
            "last_synced_at": _iso(inv_synced),
            "resource_count": int(inv_agg.resource_count or 0),
            "freshness": _staleness_label(inv_synced),
            "status": "success" if inv_agg.resource_count else "empty",
        },
        "subscriptions_catalog": {
            "last_synced_at": _iso(sub_row.synced_at if sub_row else None),
            "freshness": _staleness_label(sub_row.synced_at if sub_row else None),
            "status": "success" if sub_row else "empty",
        },
        "cost": {
            "last_synced_at": _iso(cost_row.synced_at if cost_row else None),
            "month": cost_row.month if cost_row else month_for_timeframe("MonthToDate"),
            "total_usd": round(cost_row.total_usd, 2) if cost_row else 0.0,
            "freshness": _staleness_label(cost_row.synced_at if cost_row else None),
            "status": "success" if cost_row else "empty",
        },
        "analysis": {
            "last_job_at": _iso(analysis_row.created_at if analysis_row else None),
            "last_status": analysis_row.status if analysis_row else None,
            "run_id": analysis_row.run_id if analysis_row else None,
            "open_findings": int(open_findings),
            "freshness": (
                "fresh"
                if analysis_row and analysis_row.status == "completed"
                else (analysis_row.status if analysis_row else "never")
            ),
            "status": analysis_row.status if analysis_row else ("empty" if not open_findings else "success"),
        },
        "token": get_token_cache_status(db),
    }


def get_resource_detail(db: Session, subscription_id: str, resource_id: str) -> dict[str, Any] | None:
    """Single resource from inventory with parsed properties and analysis summary."""
    sub = _normalize_sub(subscription_id)
    rid = normalize_arm_id(resource_id)
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
        return None

    items = rows_to_list([row])
    if not items:
        return None
    from app.resource_enrichment import overlay_list_rows_from_enrichment
    from app.resource_store import enrich_resource_row_costs

    detail = enrich_resource_row_costs(items[0], db, subscription_id)
    overlay_list_rows_from_enrichment(db, subscription_id, [detail])
    if str(detail.get("type") or row.resource_type or "").strip().lower() in {
        "compute/disk",
        "microsoft.compute/disks",
    }:
        from app.disk_api_enrichment import enrich_disk_api_row

        enrich_disk_api_row(detail, include_metrics=True, db=db)

    findings = (
        db.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == sub,
            OptimizationFinding.resource_id == rid,
            OptimizationFinding.status == "open",
        )
        .order_by(OptimizationFinding.estimated_savings_usd.desc())
        .limit(10)
        .all()
    )
    detail["open_findings"] = [
        {
            "id": f.id,
            "rule_id": f.rule_id,
            "severity": f.severity,
            "estimated_savings_usd": f.estimated_savings_usd,
            "detail": f.detail,
        }
        for f in findings
    ]
    detail["open_findings_count"] = len(findings)
    return detail


def get_top_spend(
    db: Session,
    subscription_id: str,
    *,
    limit: int = 10,
    timeframe: str = "MonthToDate",
) -> dict[str, Any]:
    """Top resources by MTD cost from synced cost_by_resource."""
    sub = _normalize_sub(subscription_id)
    month = month_for_timeframe(timeframe)
    rows = (
        db.query(CostByResourceSnapshot)
        .filter(
            CostByResourceSnapshot.subscription_id == sub,
            CostByResourceSnapshot.month == month,
        )
        .order_by(CostByResourceSnapshot.cost_usd.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    if not rows:
        fallback = cost_by_resource_from_db(db, subscription_id, timeframe)
        if not fallback:
            return {
                "subscription_id": sub,
                "month": month,
                "items": [],
                "source": "database",
            }
        props = fallback.get("properties") or {}
        col_names = [c.get("name") for c in props.get("columns") or []]
        items = []
        for row_vals in (props.get("rows") or [])[:limit]:
            entry = dict(zip(col_names, row_vals))
            items.append({
                "resource_id": entry.get("ResourceId"),
                "resource_type": entry.get("ResourceType"),
                "resource_group": entry.get("ResourceGroup"),
                "service_name": entry.get("ServiceName"),
                "cost_usd": entry.get("CostUSD"),
                "cost_billing": entry.get("PreTaxCost"),
                "currency": entry.get("Currency"),
            })
        return {
            "subscription_id": sub,
            "month": fallback.get("month", month),
            "billing_currency": fallback.get("billing_currency", "USD"),
            "items": items,
            "source": "database",
        }

    billing_currency = rows[0].billing_currency or "USD"
    name_by_id: dict[str, str] = {}
    if rows:
        ids = [r.resource_id for r in rows]
        inv = (
            db.query(ResourceSnapshot.resource_id, ResourceSnapshot.resource_name)
            .filter(
                ResourceSnapshot.subscription_id == sub,
                ResourceSnapshot.resource_id.in_(ids),
            )
            .all()
        )
        name_by_id = {normalize_arm_id(rid): name for rid, name in inv}

    return {
        "subscription_id": sub,
        "month": month,
        "billing_currency": billing_currency,
        "items": [
            {
                "resource_id": r.resource_id,
                "resource_name": name_by_id.get(normalize_arm_id(r.resource_id), ""),
                "resource_type": r.resource_type,
                "resource_group": r.resource_group,
                "service_name": r.service_name,
                "cost_usd": round(r.cost_usd or 0.0, 2),
                "cost_billing": round(r.cost_billing or r.cost_usd or 0.0, 2),
                "currency": r.billing_currency or billing_currency,
            }
            for r in rows
        ],
        "source": "database",
    }


def list_budgets_from_db(db: Session, subscription_id: str) -> list[dict[str, Any]]:
    sub = _normalize_sub(subscription_id)
    rows = (
        db.query(BudgetSnapshot)
        .filter(BudgetSnapshot.subscription_id == sub)
        .order_by(BudgetSnapshot.budget_name)
        .all()
    )
    return [
        {
            "id": r.id,
            "name": r.budget_name,
            "amount": r.amount,
            "timeGrain": r.time_grain,
            "currentSpend": r.current_spend,
            "forecastSpend": r.forecast_spend,
            "currency": r.currency,
            "syncedAt": _iso(r.synced_at),
        }
        for r in rows
    ]


def get_cost_dashboard_summary(db: Session, subscription_id: str, timeframe: str = "MonthToDate") -> dict[str, Any]:
    """MTD totals plus top service — wraps cost_summary_from_db."""
    summary = cost_summary_from_db(db, subscription_id, timeframe)
    if not summary:
        return {
            "subscription_id": _normalize_sub(subscription_id),
            "total_usd": 0.0,
            "total_billing": 0.0,
            "billing_currency": "USD",
            "service_count": 0,
            "source": "database",
        }
    return summary


def list_underutil_outliers(
    db: Session,
    subscription_id: str,
    *,
    limit: int = 10,
) -> dict[str, Any]:
    """Open optimization findings that indicate underutilization or waste."""
    sub = _normalize_sub(subscription_id)
    q = (
        db.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == sub,
            OptimizationFinding.status == "open",
        )
        .order_by(
            OptimizationFinding.estimated_savings_usd.desc(),
            OptimizationFinding.waste_score.desc(),
        )
    )
    rows = q.limit(max(limit * 3, 30)).all()
    items: list[dict[str, Any]] = []
    for f in rows:
        rule = (f.rule_id or "").upper()
        if not any(rule.startswith(p) or p in rule for p in _UNDERUTIL_RULE_PREFIXES):
            continue
        evidence: dict[str, Any] = {}
        try:
            evidence = json.loads(f.evidence_json or "{}")
        except Exception:
            evidence = {}
        metrics = (evidence.get("optimization_metrics") or {}).get("performance") or []
        metric_map = {m.get("id"): m.get("formatted") for m in metrics if isinstance(m, dict)}
        items.append({
            "finding_id": f.id,
            "resource_id": f.resource_id,
            "resource_name": f.resource_name,
            "resource_type": f.resource_type,
            "rule_id": f.rule_id,
            "severity": f.severity,
            "estimated_savings_usd": f.estimated_savings_usd,
            "waste_score": f.waste_score,
            "peak_cpu": metric_map.get("avg_cpu") or metric_map.get("avg_cpu_pct"),
            "detail": f.detail,
        })
        if len(items) >= limit:
            break
    return {
        "subscription_id": sub,
        "count": len(items),
        "items": items,
        "source": "optimization_findings",
    }


def list_monitor_alert_resources(
    db: Session,
    subscription_id: str,
    *,
    limit: int = 50,
) -> dict[str, Any]:
    """Metric alert rules synced as monitoring/alerts inventory rows."""
    sub = _normalize_sub(subscription_id)
    rows = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
            ResourceSnapshot.resource_type == "monitoring/alerts",
        )
        .order_by(ResourceSnapshot.resource_name)
        .limit(max(1, min(limit, 200)))
        .all()
    )
    items = []
    for r in rows:
        try:
            props = json.loads(r.properties_json or "{}")
        except Exception:
            props = {}
        items.append({
            "resource_id": r.resource_id,
            "name": r.resource_name,
            "resource_group": r.resource_group,
            "location": r.location,
            "severity": props.get("severity") or props.get("Severity"),
            "enabled": props.get("enabled", props.get("Enabled")),
            "description": props.get("description") or props.get("Description"),
            "synced_at": _iso(r.synced_at),
        })
    return {
        "subscription_id": sub,
        "count": len(items),
        "items": items,
        "source": "resource_snapshots",
    }


def list_advisor_recommendations(
    db: Session,
    subscription_id: str,
    *,
    limit: int = 50,
    min_savings: float = 0.0,
) -> dict[str, Any]:
    """Cost optimization recommendations from the internal engine (DB-backed)."""
    sub = _normalize_sub(subscription_id)
    q = (
        db.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == sub,
            OptimizationFinding.status == "open",
        )
        .order_by(OptimizationFinding.estimated_savings_usd.desc())
    )
    if min_savings > 0:
        q = q.filter(OptimizationFinding.estimated_savings_usd >= min_savings)
    rows = q.limit(max(1, min(limit, 500))).all()
    return {
        "subscription_id": sub,
        "count": len(rows),
        "total_estimated_savings_usd": round(
            sum(f.estimated_savings_usd or 0.0 for f in rows), 2,
        ),
        "items": [
            {
                "id": f.id,
                "rule_id": f.rule_id,
                "rule_name": f.rule_name,
                "category": f.category,
                "severity": f.severity,
                "resource_id": f.resource_id,
                "resource_name": f.resource_name,
                "resource_type": f.resource_type,
                "estimated_savings_usd": f.estimated_savings_usd,
                "annualized_savings_usd": f.annualized_savings_usd,
                "detail": f.detail,
                "recommendation": f.recommendation,
                "detected_at": _iso(f.detected_at),
            }
            for f in rows
        ],
        "source": "optimization_findings",
    }
