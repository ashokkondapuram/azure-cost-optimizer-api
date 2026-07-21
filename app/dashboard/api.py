"""Dashboard API — cost figures from Azure Cost Management with DB fallback."""

from __future__ import annotations

import json
import calendar
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.cost_db import (
    _MONTH_BUCKET_TIMEFRAMES,
    _PERIOD_SCOPED_TIMEFRAMES,
    _latest_cost_by_resource_month,
    cost_by_resource_type_from_db,
    cost_summary_from_db,
    daily_cost_response_from_db,
    month_for_timeframe,
)
from app.cost_live_query import (
    query_cost_summary_live,
    query_daily_costs_live,
    query_forecast_daily_live,
    query_forecast_summary_live,
)
from app.cost_resolve import resolve_cost_for_timeframe
from app.cost_explorer_sync import resource_type_display_name
from app.focus_mapping import normalize_arm_id
from app.models import (
    AdvisorRecommendation,
    AnalysisJob,
    BudgetSnapshot,
    CostByResourceSnapshot,
    CostByResourceTypeSnapshot,
    CostSyncRun,
    OptimizationFinding,
    OptimizationRun,
    ResourceSnapshot,
    SubscriptionCache,
)
from app.resource_store import get_resource_counts, rows_to_list
from app.analysis_persist import dedupe_open_findings_for_display

_UNDERUTIL_RULE_PREFIXES = (
    "VM_IDLE",
    "VM_OVERSIZE",
    "VM_RIGHTSIZE",
    "VM_SKU",
    "VM_UNDERUTILIZED",
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

_UTILIZATION_METRIC_NAMES = (
    "avg_cpu_pct",
    "avg_cpu",
    "cpu_pct",
    "max_cpu_pct",
    "memory_pct",
    "avg_memory_pct",
)

_PERF_METRIC_IDS = frozenset({
    "avg_cpu",
    "avg_cpu_pct",
    "cpu_pct",
    "max_cpu_pct",
    "memory_pct",
    "avg_memory_pct",
    "uptime_hours",
    "used_pct",
})


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


def _live_cost_token(db: Session) -> str | None:
    try:
        from app.auth import get_token

        return get_token(db)
    except Exception as exc:
        import structlog

        structlog.get_logger().warning("dashboard.cost_token_unavailable", error=str(exc)[:300])
        return None


def _enqueue_cost_sync(subscription_id: str, *, reason: str) -> None:
    from app.cost_explorer_worker import request_cost_sync

    request_cost_sync(subscription_id, reason=reason)


def _resolve_cost_summary(
    db: Session,
    subscription_id: str,
    timeframe: str,
    *,
    resource_types: list[str] | None,
    token: str | None,
    db_only: bool = False,
) -> tuple[dict | None, str | None]:
    def live_call() -> dict | None:
        if db_only or not token or resource_types:
            return None
        return query_cost_summary_live(db, subscription_id, timeframe, token=token)

    return resolve_cost_for_timeframe(
        timeframe,
        has_resource_type_filter=bool(resource_types),
        db_call=lambda: cost_summary_from_db(
            db, subscription_id, timeframe, resource_types=resource_types,
        ),
        live_call=live_call,
    )


def _resolve_daily_cost_raw(
    db: Session,
    subscription_id: str,
    timeframe: str,
    *,
    resource_types: list[str] | None,
    token: str | None,
    db_only: bool = False,
) -> tuple[dict | None, str | None]:
    def live_call() -> dict | None:
        if db_only or not token or resource_types:
            return None
        return query_daily_costs_live(db, subscription_id, timeframe, token=token)

    return resolve_cost_for_timeframe(
        timeframe,
        has_resource_type_filter=bool(resource_types),
        db_call=lambda: daily_cost_response_from_db(
            db, subscription_id, timeframe, resource_types=resource_types,
        ),
        live_call=live_call,
    )


def get_findings_summary_db(db: Session, subscription_id: str) -> dict[str, Any]:
    """Aggregated findings counts for dashboards and filter tabs."""
    from app.findings_summary import build_findings_summary
    from app.perf_cache import cached_findings_summary

    return cached_findings_summary(
        subscription_id,
        lambda: build_findings_summary(db, subscription_id),
    )


def get_advisor_findings_summary(db: Session, subscription_id: str) -> dict[str, Any]:
    """Active Azure Advisor recommendation counts from synced snapshots."""
    sub = _normalize_sub(subscription_id)
    active_filters = (
        AdvisorRecommendation.subscription_id == sub,
        AdvisorRecommendation.status == "Active",
    )
    active_count = int(
        db.query(func.count(AdvisorRecommendation.id)).filter(*active_filters).scalar() or 0
    )
    high_impact = int(
        db.query(func.count(AdvisorRecommendation.id))
        .filter(*active_filters, AdvisorRecommendation.impact == "High")
        .scalar() or 0
    )
    total_savings = float(
        db.query(func.coalesce(func.sum(AdvisorRecommendation.potential_savings_monthly), 0.0))
        .filter(*active_filters)
        .scalar() or 0.0
    )
    last_synced = (
        db.query(func.max(AdvisorRecommendation.synced_at))
        .filter(AdvisorRecommendation.subscription_id == sub)
        .scalar()
    )
    return {
        "active_count": active_count,
        "high_impact": high_impact,
        "total_savings_monthly": round(total_savings, 2),
        "last_synced": last_synced.isoformat() if last_synced else None,
        "source": "azure_advisor",
    }


def _daily_cost_from_raw(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {"points": [], "billing_currency": "CAD", "source": "database"}
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
    source = raw.get("source") or "database"
    return {
        "points": points,
        "billing_currency": raw.get("billing_currency") or "CAD",
        "source": source,
    }


def _compact_daily_cost(
    db: Session,
    subscription_id: str,
    timeframe: str = "MonthToDate",
    *,
    resource_types: list[str] | None = None,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if raw is None:
        token = _live_cost_token(db)
        raw, _source = _resolve_daily_cost_raw(
            db,
            subscription_id,
            timeframe,
            resource_types=resource_types,
            token=token,
        )
    if not raw:
        return {"points": [], "billing_currency": "CAD", "source": "database"}
    return _daily_cost_from_raw(raw)


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


def _point_cost(point: dict[str, Any]) -> float:
    return float(point.get("cost_billing") or point.get("cost_usd") or 0)


def _point_month_key(point: dict[str, Any]) -> str | None:
    raw = point.get("date")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.strftime("%Y-%m")
    text = str(raw).strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}"
    if len(text) >= 7 and text[4] == "-":
        return text[:7]
    if len(text) >= 7 and text[4] == "/":
        parts = text.split("/")
        if len(parts) >= 3:
            return f"{parts[2]}-{parts[0].zfill(2)}"
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%Y-%m")
    except ValueError:
        return None


def _monthly_cost_trend_from_points(
    points: list[dict[str, Any]],
    *,
    mtd_amount: float | None = None,
) -> dict[str, Any]:
    if not points:
        return {"projected": 0.0, "last_month": 0.0, "delta_pct": None}

    today = date.today()
    current_key = today.strftime("%Y-%m")
    first_of_month = today.replace(day=1)
    last_month_end = first_of_month - timedelta(days=1)
    last_key = last_month_end.strftime("%Y-%m")

    current_mtd = float(mtd_amount or 0)
    if current_mtd <= 0:
        current_mtd = sum(
            _point_cost(point)
            for point in points
            if _point_month_key(point) == current_key
        )

    days_in_month = calendar.monthrange(today.year, today.month)[1]
    days_elapsed = max(1, today.day)
    projected = round(current_mtd * (days_in_month / days_elapsed), 2)

    last_month_total = round(
        sum(
            _point_cost(point)
            for point in points
            if _point_month_key(point) == last_key
        ),
        2,
    )

    delta_pct = None
    delta_usd = None
    if last_month_total > 0:
        delta_pct = round(((projected - last_month_total) / last_month_total) * 100, 1)
        delta_usd = round(projected - last_month_total, 2)

    prorated_last_mtd = 0.0
    if last_month_total > 0 and days_in_month > 0:
        prorated_last_mtd = round(last_month_total * (days_elapsed / days_in_month), 2)
    mtd_delta_usd = round(current_mtd - prorated_last_mtd, 2) if last_month_total > 0 else None

    return {
        "projected": projected,
        "last_month": last_month_total,
        "delta_pct": delta_pct,
        "delta_usd": delta_usd,
        "mtd_delta_usd": mtd_delta_usd,
        "forecast_source": "prorated_mtd" if current_mtd > 0 else "none",
    }


def _monthly_cost_trend_from_api(
    db: Session,
    subscription_id: str,
    *,
    mtd_summary: dict[str, Any],
    token: str | None,
) -> dict[str, Any]:
    from app.cost_live_bundle import monthly_cost_trend_from_summaries

    mtd_amount = float(mtd_summary.get("pretax_total") or mtd_summary.get("cost_usd_total") or 0)
    last_month = query_cost_summary_live(
        db, subscription_id, "TheLastMonth", token=token,
    ) or {}
    forecast = query_forecast_summary_live(db, subscription_id, token=token) or {}
    return monthly_cost_trend_from_summaries(
        mtd_amount=mtd_amount,
        last_month=last_month,
        forecast=forecast,
    )


def _weekly_cost_from_daily_points(points: list[dict[str, Any]]) -> dict[str, Any]:
    """Last 7 days vs prior 7 days using Azure daily cost rows (no local rate projection)."""
    if not points:
        return {"amount": 0.0, "delta_pct": None, "days": 0}
    sorted_pts = sorted(points, key=lambda p: p.get("date") or "")
    recent = sorted_pts[-7:]
    prior = sorted_pts[-14:-7]
    amount = round(sum(_point_cost(p) for p in recent), 2)
    prior_amount = sum(_point_cost(p) for p in prior)
    delta_pct = None
    delta_usd = None
    if prior_amount > 0:
        delta_pct = round(((amount - prior_amount) / prior_amount) * 100, 1)
        delta_usd = round(amount - prior_amount, 2)
    return {"amount": amount, "delta_pct": delta_pct, "delta_usd": delta_usd, "days": len(recent)}


def _weekly_cost_from_points(points: list[dict[str, Any]]) -> dict[str, Any]:
    if not points:
        return {"amount": 0.0, "delta_pct": None, "days": 0}
    sorted_pts = sorted(points, key=lambda p: p.get("date") or "")
    recent = sorted_pts[-7:]
    prior = sorted_pts[-14:-7] if len(sorted_pts) >= 8 else []
    amount = sum(p.get("cost_billing") or p.get("cost_usd") or 0 for p in recent)
    prior_amount = sum(p.get("cost_billing") or p.get("cost_usd") or 0 for p in prior)
    delta_pct = None
    delta_usd = None
    if prior_amount > 0:
        delta_pct = round(((amount - prior_amount) / prior_amount) * 100, 1)
        delta_usd = round(amount - prior_amount, 2)
    elif prior:
        delta_usd = round(amount - prior_amount, 2)
    return {
        "amount": round(amount, 2),
        "delta_pct": delta_pct,
        "delta_usd": delta_usd,
        "days": len(recent),
    }


def _resource_health_counts(db: Session, subscription_id: str, total_resources: int) -> dict[str, Any]:
    """Health breakdown from Azure Resource Health + synced inventory signals."""
    from app.resource_health import get_subscription_health_counts

    result = get_subscription_health_counts(db, subscription_id)
    if not result.get("total"):
        return {
            "healthy": 0,
            "degraded": 0,
            "unavailable": 0,
            "unknown": max(0, int(total_resources or 0)),
            "total": int(total_resources or 0),
            "source": "inventory_properties",
        }
    return result


def _utilization_type_label(resource_type: str) -> str:
    canon = (resource_type or "").strip()
    if not canon:
        return "Other"
    if "/" in canon:
        return resource_type_display_name("", canon)
    return canon.replace("_", " ").title()


def _format_utilization_pct(value: float | None) -> str | None:
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n <= 1.0:
        n *= 100.0
    return f"{n:.1f}%"


def _utilization_buckets_to_items(
    buckets: dict[str, dict[str, Any]],
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for label, bucket in sorted(buckets.items(), key=lambda x: (-x[1]["count"], x[0])):
        avg_pct = bucket.get("avg_pct")
        utilization_label = _format_utilization_pct(avg_pct) if avg_pct is not None else None
        if not utilization_label and bucket.get("samples"):
            utilization_label = str(bucket["samples"][0])
        if not utilization_label and bucket.get("source") == "findings":
            utilization_label = "Open findings"
        out.append({
            "type": label,
            "count": int(bucket["count"]),
            "utilization_label": utilization_label or "—",
            "avg_utilization_pct": round(avg_pct, 1) if avg_pct is not None else None,
        })
        if len(out) >= limit:
            break
    return out


def _is_underutil_candidate(rule_id: str | None, evidence: dict[str, Any]) -> bool:
    metrics = (evidence.get("optimization_metrics") or {}).get("performance") or []
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        status = (metric.get("status") or "").lower()
        if status in ("underutilized", "idle", "low"):
            return True
    rule = (rule_id or "").upper()
    if any(rule.startswith(prefix) or prefix in rule for prefix in _UNDERUTIL_RULE_PREFIXES):
        return True
    if _peak_metric_from_evidence(evidence):
        return True
    waste_keywords = (
        "IDLE", "UNDERUTIL", "OVERSIZE", "RIGHTSIZE", "LOW_UTIL", "WASTE", "DEALLOCATE",
    )
    return any(keyword in rule for keyword in waste_keywords)


def _resource_display_names(
    db: Session,
    subscription_id: str,
    resource_ids: list[str],
) -> dict[str, str]:
    sub = _normalize_sub(subscription_id)
    ids = {normalize_arm_id(rid) for rid in resource_ids if rid}
    if not ids:
        return {}
    rows = (
        db.query(ResourceSnapshot.resource_id, ResourceSnapshot.resource_name)
        .filter(
            func.lower(ResourceSnapshot.subscription_id) == sub,
            func.lower(ResourceSnapshot.resource_id).in_(list(ids)),
        )
        .all()
    )
    return {
        normalize_arm_id(rid): name
        for rid, name in rows
        if rid and name
    }


def _top_resource_spend_items(
    db: Session,
    subscription_id: str,
    *,
    limit: int = 10,
    timeframe: str = "MonthToDate",
) -> list[dict[str, Any]]:
    """Top individual resources by MTD cost from cost_by_resource."""
    sub = _normalize_sub(subscription_id)
    month = month_for_timeframe(timeframe)

    def _query(month_key: str) -> list[CostByResourceSnapshot]:
        return (
            db.query(CostByResourceSnapshot)
            .filter(
                func.lower(CostByResourceSnapshot.subscription_id) == sub,
                CostByResourceSnapshot.month == month_key,
            )
            .order_by(
                CostByResourceSnapshot.cost_billing.desc().nullslast(),
                CostByResourceSnapshot.cost_usd.desc(),
            )
            .limit(limit)
            .all()
        )

    rows = _query(month)
    if not rows:
        latest = _latest_cost_by_resource_month(db, subscription_id)
        if latest and latest != month:
            rows = _query(latest)
    if not rows:
        return []

    names = _resource_display_names(db, subscription_id, [r.resource_id for r in rows])
    items: list[dict[str, Any]] = []
    for row in rows:
        rid = normalize_arm_id(row.resource_id)
        items.append({
            "resource_id": rid,
            "display_name": (
                names.get(rid)
                or row.service_name
                or (rid.split("/")[-1] if rid else "Resource")
            ),
            "resource_type": row.resource_type,
            "service_name": row.service_name,
            "cost_billing": round(float(row.cost_billing or row.cost_usd or 0), 2),
            "cost_usd": round(float(row.cost_usd or 0), 2),
            "currency": row.billing_currency or "CAD",
        })
    return items


def _mtd_cost_by_resource_ids(
    db: Session,
    subscription_id: str,
    resource_ids: list[str],
    *,
    timeframe: str = "MonthToDate",
) -> dict[str, float]:
    sub = _normalize_sub(subscription_id)
    ids = {normalize_arm_id(rid) for rid in resource_ids if rid}
    if not ids:
        return {}

    from app.resource_enrichment import mtd_costs_map_from_enrichment

    enriched = mtd_costs_map_from_enrichment(db, subscription_id, list(ids))
    missing = [rid for rid in ids if rid not in enriched]
    if not missing:
        return enriched

    month = month_for_timeframe(timeframe)
    rows = (
        db.query(CostByResourceSnapshot.resource_id, CostByResourceSnapshot.cost_billing, CostByResourceSnapshot.cost_usd)
        .filter(
            func.lower(CostByResourceSnapshot.subscription_id) == sub,
            CostByResourceSnapshot.month == month,
            func.lower(CostByResourceSnapshot.resource_id).in_(missing),
        )
        .all()
    )
    if not rows:
        latest = _latest_cost_by_resource_month(db, subscription_id)
        if latest and latest != month:
            rows = (
                db.query(CostByResourceSnapshot.resource_id, CostByResourceSnapshot.cost_billing, CostByResourceSnapshot.cost_usd)
                .filter(
                    func.lower(CostByResourceSnapshot.subscription_id) == sub,
                    CostByResourceSnapshot.month == latest,
                    func.lower(CostByResourceSnapshot.resource_id).in_(missing),
                )
                .all()
            )
    legacy = {
        normalize_arm_id(rid): round(float(cost_billing or cost_usd or 0), 2)
        for rid, cost_billing, cost_usd in rows
        if rid
    }
    return {**legacy, **enriched}


def _latest_utilization_by_resource(
    db: Session,
    subscription_id: str,
    resource_ids: list[str],
) -> dict[str, str]:
    """Latest avg CPU (or similar) per resource for dashboard cost-vs-util panels."""
    from app.resource_enrichment import utilization_map_from_enrichment

    return utilization_map_from_enrichment(db, subscription_id, resource_ids)


def _peak_metric_from_evidence(evidence: dict[str, Any]) -> str | None:
    metrics = (evidence.get("optimization_metrics") or {}).get("performance") or []
    metric_map = {
        m.get("id"): m.get("formatted")
        for m in metrics
        if isinstance(m, dict) and m.get("id")
    }
    for key in ("avg_cpu", "avg_cpu_pct", "cpu_pct", "memory_pct", "avg_memory_pct", "used_pct"):
        if metric_map.get(key):
            return str(metric_map[key])
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        if metric.get("id") in _PERF_METRIC_IDS and metric.get("formatted"):
            return str(metric["formatted"])
    return None


def _utilization_from_findings(
    db: Session,
    subscription_id: str,
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    sub = _normalize_sub(subscription_id)
    rows = (
        db.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == sub,
            OptimizationFinding.status == "open",
            OptimizationFinding.resource_type.isnot(None),
            OptimizationFinding.resource_type != "",
        )
        .order_by(OptimizationFinding.estimated_savings_usd.desc())
        .limit(500)
        .all()
    )
    deduped = dedupe_open_findings_for_display(rows)
    buckets: dict[str, dict[str, Any]] = {}
    for finding in deduped:
        try:
            evidence = json.loads(finding.evidence_json or "{}")
        except Exception:
            evidence = {}
        peak = _peak_metric_from_evidence(evidence)
        if not peak:
            continue
        label = _utilization_type_label(finding.resource_type or "")
        bucket = buckets.setdefault(label, {"count": 0, "samples": [], "source": "findings"})
        bucket["count"] += 1
        bucket["samples"].append(peak)
    return _utilization_buckets_to_items(buckets, limit=limit)


def _utilization_from_open_findings(
    db: Session,
    subscription_id: str,
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Fallback: open finding counts by resource type when no utilization metrics exist."""
    sub = _normalize_sub(subscription_id)
    rows = (
        db.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == sub,
            OptimizationFinding.status == "open",
            OptimizationFinding.resource_type.isnot(None),
            OptimizationFinding.resource_type != "",
        )
        .order_by(OptimizationFinding.estimated_savings_usd.desc())
        .limit(500)
        .all()
    )
    deduped = dedupe_open_findings_for_display(rows)
    buckets: dict[str, dict[str, Any]] = {}
    for finding in deduped:
        label = _utilization_type_label(finding.resource_type or "")
        bucket = buckets.setdefault(label, {"count": 0, "samples": [], "source": "findings"})
        bucket["count"] += 1
    return _utilization_buckets_to_items(buckets, limit=limit)


def utilization_by_resource_type(
    db: Session,
    subscription_id: str,
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Insights chart data — enrichment metrics, then findings."""
    from app.resource_enrichment import utilization_by_type_from_enrichment

    items = utilization_by_type_from_enrichment(db, subscription_id, limit=limit)
    if items:
        return items
    items = _utilization_from_findings(db, subscription_id, limit=limit)
    if items:
        return items
    return _utilization_from_open_findings(db, subscription_id, limit=limit)


def _utilization_by_type(underutil_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Legacy adapter for underutil outlier rows."""
    buckets: dict[str, dict[str, Any]] = {}
    for item in underutil_items:
        label = _utilization_type_label(item.get("resource_type") or "other")
        bucket = buckets.setdefault(label, {"count": 0, "samples": [], "source": "underutil"})
        bucket["count"] += 1
        util = item.get("peak_cpu")
        if util:
            bucket["samples"].append(str(util))
    return _utilization_buckets_to_items(buckets)


def _cost_vs_utilization(
    db: Session,
    subscription_id: str,
    top_spend_items: list[dict[str, Any]],
    underutil_items: list[dict[str, Any]],
    *,
    timeframe: str = "MonthToDate",
) -> list[dict[str, Any]]:
    resource_spend = _top_resource_spend_items(
        db, subscription_id, limit=10, timeframe=timeframe,
    )
    spend_rows = resource_spend or [
        item for item in top_spend_items[:10]
        if item.get("resource_id")
    ]
    util_by_id = {
        normalize_arm_id(i.get("resource_id", "")): i
        for i in underutil_items
        if i.get("resource_id")
    }
    spend_ids = [
        normalize_arm_id(item.get("resource_id", ""))
        for item in spend_rows
        if item.get("resource_id")
    ]
    history_util = _latest_utilization_by_resource(db, subscription_id, spend_ids)
    merged: list[dict[str, Any]] = []
    for item in spend_rows:
        rid = normalize_arm_id(item.get("resource_id", ""))
        util = util_by_id.get(rid) or {}
        cost = item.get("cost_billing") or item.get("cost_usd") or 0
        name = (
            item.get("display_name")
            or item.get("resource_name")
            or (rid.split("/")[-1] if rid else None)
            or item.get("arm_resource_type")
            or "Resource"
        )
        utilization = (
            util.get("peak_cpu")
            or util.get("avg_cpu")
            or history_util.get(rid)
            or "—"
        )
        util_pct = None
        if utilization and utilization != "—":
            try:
                util_pct = float(str(utilization).replace("%", "").strip())
            except (TypeError, ValueError):
                util_pct = None
        merged.append({
            "resource_id": rid or None,
            "resource_type": item.get("arm_resource_type") or item.get("resource_type"),
            "name": name,
            "cost": round(float(cost), 2),
            "utilization": utilization,
            "utilization_pct": util_pct,
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
    findings_summary: dict[str, Any] | None = None,
    advisor_summary: dict[str, Any] | None = None,
    resource_types: list[str] | None = None,
    monthly_trend: dict[str, Any] | None = None,
    forecast_daily_points: list[dict[str, Any]] | None = None,
    weekly_points: list[dict[str, Any]] | None = None,
    timeframe: str = "MonthToDate",
) -> dict[str, Any]:
    """KPI row + dashboard panels (data only — no boilerplate copy)."""
    total_resources = int(
        inventory_counts.get("cost_bearing_inventory")
        if inventory_counts.get("cost_bearing_inventory") is not None
        else inventory_counts.get("inventory_total") or 0
    )
    health = _resource_health_counts(db, subscription_id, total_resources)
    mtd_amount = cost_summary.get("pretax_total") or cost_summary.get("cost_usd_total") or 0
    weekly_source_points = weekly_points if weekly_points is not None else daily_points
    weekly = _weekly_cost_from_daily_points(weekly_source_points)
    if monthly_trend is None:
        monthly_trend = _monthly_cost_trend_from_points(
            daily_points, mtd_amount=float(mtd_amount or 0),
        )
    open_findings = int((findings_summary or {}).get("open_findings") or 0)
    cost_resources = int(inventory_counts.get("cost_resources") or 0)

    weekly_sub: str | None = None
    if weekly["delta_pct"] is not None:
        weekly_sub = (
            f"{'↓' if (weekly['delta_pct'] or 0) < 0 else '↑'} "
            f"{abs(weekly['delta_pct'])}% vs prior week"
        )
    elif mtd_amount:
        weekly_sub = f"MTD {round(float(mtd_amount), 2):,.2f} {billing_currency}"

    monthly_sub_parts: list[str] = []
    if monthly_trend.get("forecast_source") == "azure_forecast":
        monthly_sub_parts.append("Azure Cost Management forecast")
    elif monthly_trend.get("forecast_source") == "prorated_mtd":
        monthly_sub_parts.append("Estimated from month-to-date run rate")
    if monthly_trend["delta_pct"] is not None:
        monthly_sub_parts.append(
            f"{'↓' if (monthly_trend['delta_pct'] or 0) < 0 else '↑'} "
            f"{abs(monthly_trend['delta_pct'])}% vs last month"
        )
    elif monthly_trend["last_month"] > 0:
        monthly_sub_parts.append(
            f"Last month {monthly_trend['last_month']:,.2f} {billing_currency}"
        )
    monthly_sub = " · ".join(monthly_sub_parts) if monthly_sub_parts else None

    est_savings = round(float((findings_summary or {}).get("total_estimated_savings_usd") or 0), 2)
    advisor = advisor_summary or get_advisor_findings_summary(db, subscription_id)
    advisor_sub: str | None = None
    if advisor["high_impact"]:
        advisor_sub = f"{advisor['high_impact']} high impact"
    elif advisor["total_savings_monthly"] > 0:
        advisor_sub = (
            f"{advisor['total_savings_monthly']:,.0f} {billing_currency} potential/mo"
        )
    elif advisor["active_count"] == 0:
        advisor_sub = "Sync from Optimization center"

    return {
        "hero_actions": [
            {"id": "recommendations", "label": "View actions", "href": "/action-centre?hasAction=1"},
            {"id": "findings", "label": "Findings summary", "href": "/dashboard#findings-insights"},
            {"id": "costs", "label": "Cost explorer", "href": "/costs"},
        ],
        "hero_deltas": {
            "mtd_delta_usd": monthly_trend.get("mtd_delta_usd"),
        },
        "kpis": [
            {
                "id": "total_resources",
                "label": "Resources with cost",
                "value": total_resources,
                "tone": "default",
                **(
                    {"sub": f"{cost_resources:,} billed in Cost Management"}
                    if cost_resources
                    else {}
                ),
            },
            {
                "id": "resources_degraded",
                "label": "Degraded resources",
                "value": health["degraded"],
                "tone": "warn" if health["degraded"] else "default",
            },
            {
                "id": "advisor_findings",
                "label": "Advisor findings",
                "value": advisor["active_count"],
                "tone": "warn" if advisor["active_count"] else "default",
                "href": "/dashboard#findings-insights",
                **({"sub": advisor_sub} if advisor_sub else {}),
            },
            {
                "id": "resources_unavailable",
                "label": "Unavailable resources",
                "value": health["unavailable"],
                "tone": "danger" if health["unavailable"] else "default",
            },
            {
                "id": "weekly_cost",
                "label": "Weekly cost",
                "value": weekly["amount"],
                "currency": billing_currency,
                "tone": "default",
                **({"sub": weekly_sub} if weekly_sub else {}),
                **({"delta_pct": weekly["delta_pct"]} if weekly.get("delta_pct") is not None else {}),
                **({"delta_usd": weekly["delta_usd"]} if weekly.get("delta_usd") is not None else {}),
            },
            {
                "id": "monthly_trend",
                "label": "Forecast monthly cost",
                "value": monthly_trend["projected"],
                "currency": billing_currency,
                "tone": "default",
                **({"sub": monthly_sub} if monthly_sub else {}),
                **({"delta_pct": monthly_trend["delta_pct"]} if monthly_trend.get("delta_pct") is not None else {}),
                **({"delta_usd": monthly_trend["delta_usd"]} if monthly_trend.get("delta_usd") is not None else {}),
            },
            {
                "id": "open_findings",
                "label": "Open findings",
                "value": open_findings,
                "tone": "warn",
                "href": "/dashboard#findings-insights",
            },
            {
                "id": "estimated_savings",
                "label": "Est. savings/mo",
                "value": est_savings,
                "currency": billing_currency,
                "tone": "success",
            },
        ],
        "panels": {
            "daily_cost_trend": {
                "title": "Daily cost trend",
                "points": daily_points[-14:],
                "forecast_points": forecast_daily_points or [],
                "currency": billing_currency,
                "monthly_comparison": monthly_trend,
            },
            "utilization_by_resource": {
                "title": "Utilization by resource type",
                "items": utilization_by_resource_type(db, subscription_id),
            },
            "cost_vs_utilization": {
                "title": "Cost vs utilization",
                "items": _cost_vs_utilization(
                    db,
                    subscription_id,
                    top_spend_items,
                    underutil_items,
                    timeframe=timeframe,
                ),
            },
            "resource_health_status": {
                "title": "Resource health",
                "source": health.get("source"),
                "segments": [
                    {"name": "Healthy", "value": health["healthy"], "key": "healthy"},
                    {"name": "Degraded", "value": health["degraded"], "key": "degraded"},
                    {"name": "Unavailable", "value": health["unavailable"], "key": "unavailable"},
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
    resource_types: list[str] | None = None,
    top_spend_limit: int = 8,
    advisor_limit: int = 6,
    underutil_limit: int = 6,
    alerts_limit: int = 8,
    runs_limit: int = 10,
) -> dict[str, Any]:
    """Single PostgreSQL-backed payload for the dashboard (one round trip)."""
    from app.perf_cache import cached_dashboard_overview

    sub = _normalize_sub(subscription_id)
    types_key = ",".join(sorted(resource_types or []))
    cache_key = (
        f"{sub}:{timeframe}:{types_key}:{top_spend_limit}:{advisor_limit}:"
        f"{underutil_limit}:{alerts_limit}:{runs_limit}"
    )
    return cached_dashboard_overview(
        cache_key,
        lambda: _get_dashboard_overview_uncached(
            db,
            subscription_id,
            timeframe=timeframe,
            resource_types=resource_types,
            top_spend_limit=top_spend_limit,
            advisor_limit=advisor_limit,
            underutil_limit=underutil_limit,
            alerts_limit=alerts_limit,
            runs_limit=runs_limit,
        ),
    )


def _get_dashboard_overview_uncached(
    db: Session,
    subscription_id: str,
    *,
    timeframe: str = "MonthToDate",
    resource_types: list[str] | None = None,
    top_spend_limit: int = 8,
    advisor_limit: int = 6,
    underutil_limit: int = 6,
    alerts_limit: int = 8,
    runs_limit: int = 10,
) -> dict[str, Any]:
    sub = _normalize_sub(subscription_id)
    # Dashboard reads synced PostgreSQL first — live Azure Cost Management is slow and
    # runs on background cost sync instead of blocking the overview request.
    db_only = not resource_types
    token = _live_cost_token(db) if not db_only else None

    cost_summary, cost_source = _resolve_cost_summary(
        db, subscription_id, timeframe, resource_types=resource_types, token=token, db_only=db_only,
    )
    if not cost_summary:
        cost_summary = {}
        _enqueue_cost_sync(sub, reason="dashboard_no_cost_data")
    elif cost_source != "database":
        _enqueue_cost_sync(sub, reason="dashboard_live_fallback")

    if timeframe == "ThisYear":
        ytd_summary = cost_summary
    else:
        ytd_row, _ytd_source = _resolve_cost_summary(
            db,
            subscription_id,
            "ThisYear",
            resource_types=resource_types,
            token=token,
            db_only=db_only,
        )
        ytd_summary = ytd_row or {
            "pretax_total": 0.0,
            "cost_usd_total": 0.0,
            "billing_currency": cost_summary.get("billing_currency") or "CAD",
            "source": "database",
        }

    daily_raw, daily_source = _resolve_daily_cost_raw(
        db, subscription_id, timeframe, resource_types=resource_types, token=token, db_only=db_only,
    )
    daily = _daily_cost_from_raw(daily_raw) if daily_raw else {
        "points": [],
        "billing_currency": cost_summary.get("billing_currency") or "CAD",
        "source": daily_source or "database",
    }

    daily_points = daily.get("points") or []
    mtd_amount = float(cost_summary.get("pretax_total") or cost_summary.get("cost_usd_total") or 0)
    monthly_trend = _monthly_cost_trend_from_points(daily_points, mtd_amount=mtd_amount)

    weekly_points: list[dict[str, Any]] | None = None
    if db_only:
        weekly_raw, _weekly_source = _resolve_daily_cost_raw(
            db,
            subscription_id,
            "Last14Days",
            resource_types=None,
            token=None,
            db_only=True,
        )
        if weekly_raw:
            weekly_points = _daily_cost_from_raw(weekly_raw).get("points") or []

    inventory_counts = get_resource_counts(db, subscription_id)
    underutil = list_underutil_outliers(db, subscription_id, limit=underutil_limit)
    top_spend = get_top_spend(
        db, subscription_id, limit=top_spend_limit, timeframe=timeframe,
    )
    spend_by_id = {
        normalize_arm_id(item.get("resource_id", "")): item
        for item in (top_spend.get("items") or [])
        if item.get("resource_id")
    }
    mtd_costs = _mtd_cost_by_resource_ids(
        db,
        subscription_id,
        [item.get("resource_id", "") for item in (underutil.get("items") or [])],
        timeframe=timeframe,
    )
    for item in underutil.get("items") or []:
        rid = normalize_arm_id(item.get("resource_id", ""))
        item["mtd_cost"] = (
            mtd_costs.get(rid)
            or (spend_by_id.get(rid) or {}).get("cost_billing")
            or (spend_by_id.get(rid) or {}).get("cost_usd")
        )
    billing_currency = (
        daily.get("billing_currency")
        or top_spend.get("billing_currency")
        or cost_summary.get("billing_currency")
        or "CAD"
    )
    findings_summary = get_findings_summary_db(db, subscription_id)
    advisor_summary = get_advisor_findings_summary(db, sub)
    effective_cost_source = (
        cost_source
        or daily_source
        or cost_summary.get("source")
        or daily.get("source")
        or "database"
    )
    return {
        "subscription_id": sub,
        "data_source": "azure_cost_management" if effective_cost_source == "azure" else "postgresql",
        "timeframe": timeframe,
        "resource_types": resource_types or [],
        "sync": get_sync_status(db, subscription_id),
        "portal": _build_portal_section(
            db,
            subscription_id,
            inventory_counts=inventory_counts,
            daily_points=daily_points,
            billing_currency=billing_currency,
            underutil_items=underutil.get("items") or [],
            top_spend_items=top_spend.get("items") or [],
            cost_summary=cost_summary,
            findings_summary=findings_summary,
            advisor_summary=advisor_summary,
            resource_types=resource_types,
            monthly_trend=monthly_trend,
            forecast_daily_points=[],
            weekly_points=weekly_points,
            timeframe=timeframe,
        ),
        "cost": {
            "summary": cost_summary,
            "ytd": ytd_summary,
            "daily": daily,
            "top_spend": top_spend,
        },
        "optimization": {
            "summary": findings_summary,
            "advisor": advisor_summary,
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

    from app.cost_period_totals import latest_ytd_from_db, list_period_totals_from_db
    ytd_row = latest_ytd_from_db(db, sub)
    period_totals = list_period_totals_from_db(db, sub)

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
    from app.cost_explorer_worker import is_cost_sync_pending, last_cost_sync_error
    from app.cost_query_cache import cost_cache_metrics
    from app.perf_cache import perf_cache_metrics

    return {
        "subscription_id": sub,
        "data_source": "postgresql",
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
            "pending": is_cost_sync_pending(sub),
            "month": cost_row.month if cost_row else month_for_timeframe("MonthToDate"),
            "total_billing": round(cost_row.total_billing, 2) if cost_row else 0.0,
            "total_usd": round(cost_row.total_usd, 2) if cost_row else 0.0,
            "billing_currency": (cost_row.billing_currency if cost_row else None) or "CAD",
            "freshness": _staleness_label(cost_row.synced_at if cost_row else None),
            "last_error": last_cost_sync_error(sub),
            "status": (
                "pending"
                if is_cost_sync_pending(sub)
                else (
                    "empty"
                    if not cost_row
                    or (
                        float(cost_row.total_billing or 0) <= 0
                        and float(cost_row.total_usd or 0) <= 0
                    )
                    else "success"
                )
            ),
            "ytd_total_billing": ytd_row.get("pretax_total") if ytd_row else None,
            "ytd_period_end": ytd_row.get("period_end") if ytd_row else None,
            "ytd_synced_at": ytd_row.get("synced_at") if ytd_row else None,
            "period_totals": period_totals,
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
        "cost_cache": cost_cache_metrics(),
        "read_cache": perf_cache_metrics(),
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

    norm_rid = normalize_arm_id(rid)
    findings = dedupe_open_findings_for_display([
        row
        for row in db.query(OptimizationFinding)
        .filter(
            func.lower(OptimizationFinding.subscription_id) == sub,
            OptimizationFinding.status == "open",
        )
        .order_by(OptimizationFinding.estimated_savings_usd.desc())
        .all()
        if normalize_arm_id(row.resource_id or "") == norm_rid
    ])[:10]
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
    """Top resource types by MTD cost (cost explorer worker data)."""
    sub = _normalize_sub(subscription_id)
    if timeframe not in _MONTH_BUCKET_TIMEFRAMES:
        return {
            "subscription_id": sub,
            "month": month_for_timeframe(timeframe),
            "items": [],
            "source": "database",
            "granularity": "resource_type",
        }
    month = month_for_timeframe(timeframe)
    cap = max(1, min(limit, 100))

    def _query_for_month(m: str) -> list:
        return (
            db.query(CostByResourceTypeSnapshot)
            .filter(
                CostByResourceTypeSnapshot.subscription_id == sub,
                CostByResourceTypeSnapshot.month == m,
            )
            .order_by(
                CostByResourceTypeSnapshot.cost_billing.desc(),
                CostByResourceTypeSnapshot.cost_usd.desc(),
            )
            .limit(cap)
            .all()
        )

    rows = _query_for_month(month)
    if not rows and timeframe not in _PERIOD_SCOPED_TIMEFRAMES:
        latest = (
            db.query(func.max(CostByResourceTypeSnapshot.month))
            .filter(CostByResourceTypeSnapshot.subscription_id == sub)
            .scalar()
        )
        if latest and latest != month:
            month = latest
            rows = _query_for_month(month)
    if not rows:
        fallback = cost_by_resource_type_from_db(db, subscription_id, timeframe)
        if not fallback:
            return {
                "subscription_id": sub,
                "month": month,
                "items": [],
                "source": "database",
                "granularity": "resource_type",
            }
        props = fallback.get("properties") or {}
        col_names = [c.get("name") for c in props.get("columns") or []]
        items = []
        for row_vals in (props.get("rows") or [])[:limit]:
            entry = dict(zip(col_names, row_vals))
            items.append({
                "arm_resource_type": entry.get("ResourceType"),
                "display_name": entry.get("DisplayName"),
                "resource_type": entry.get("ResourceType"),
                "cost_usd": entry.get("CostUSD"),
                "cost_billing": entry.get("PreTaxCost"),
                "currency": entry.get("Currency"),
            })
        return {
            "subscription_id": sub,
            "month": fallback.get("month", month),
            "billing_currency": fallback.get("billing_currency") or "CAD",
            "items": items,
            "source": "database",
            "granularity": "resource_type",
        }

    billing_currency = rows[0].billing_currency or "CAD"
    return {
        "subscription_id": sub,
        "month": month,
        "billing_currency": billing_currency,
        "granularity": "resource_type",
        "items": [
            {
                "arm_resource_type": r.arm_resource_type,
                "canonical_resource_type": r.canonical_resource_type,
                "display_name": resource_type_display_name(r.arm_resource_type, r.canonical_resource_type),
                "resource_type": r.canonical_resource_type or r.arm_resource_type,
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


def get_cost_dashboard_summary(
    db: Session,
    subscription_id: str,
    timeframe: str = "MonthToDate",
    *,
    resource_types: list[str] | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Subscription totals — synced DB first, then live Azure."""
    live_token = token if token is not None else _live_cost_token(db)
    summary, _source = _resolve_cost_summary(
        db,
        subscription_id,
        timeframe,
        resource_types=resource_types,
        token=live_token,
    )
    if summary:
        return summary
    return {
        "subscription_id": _normalize_sub(subscription_id),
        "pretax_total": 0.0,
        "cost_usd_total": 0.0,
        "billing_currency": "CAD",
        "service_count": 0,
        "source": "database",
        "sync_required": True,
    }


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
            func.lower(OptimizationFinding.subscription_id) == sub,
            OptimizationFinding.status == "open",
        )
        .order_by(
            OptimizationFinding.estimated_savings_usd.desc(),
            OptimizationFinding.waste_score.desc(),
        )
    )
    rows = dedupe_open_findings_for_display(q.limit(max(limit * 5, 50)).all())
    items: list[dict[str, Any]] = []
    for f in rows:
        evidence: dict[str, Any] = {}
        try:
            evidence = json.loads(f.evidence_json or "{}")
        except Exception:
            evidence = {}
        if not _is_underutil_candidate(f.rule_id, evidence):
            continue
        metrics = (evidence.get("optimization_metrics") or {}).get("performance") or []
        metric_map = {m.get("id"): m.get("formatted") for m in metrics if isinstance(m, dict)}
        peak_cpu = (
            _peak_metric_from_evidence(evidence)
            or metric_map.get("avg_cpu")
            or metric_map.get("avg_cpu_pct")
        )
        items.append({
            "finding_id": f.id,
            "resource_id": f.resource_id,
            "resource_name": f.resource_name,
            "resource_type": f.resource_type,
            "rule_id": f.rule_id,
            "severity": f.severity,
            "estimated_savings_usd": f.estimated_savings_usd,
            "waste_score": f.waste_score,
            "peak_cpu": peak_cpu,
            "avg_cpu": peak_cpu,
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
    rows = dedupe_open_findings_for_display(
        q.limit(max(1, min(limit * 3, 500))).all()
    )[: max(1, min(limit, 500))]
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
