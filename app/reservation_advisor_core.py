"""Reservation advisor — merge Azure live data, Advisor, and engine findings."""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.azure_reservations import fetch_live_commitments
from app.models import AdvisorRecommendation, CostByServiceSnapshot, OptimizationFinding

log = structlog.get_logger()

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

_RESERVATION_KEYWORDS = re.compile(
    r"reservation|reserved instance|savings plan|purchase reservation|right-size reservation|commitment",
    re.I,
)

_UNDERUTIL_THRESHOLD = 80.0


def _normalize_sub(sub: str) -> str:
    return (sub or "").strip().lower()


def _extract_evidence(finding: Any) -> dict:
    ev = getattr(finding, "evidence", {}) or {}
    if isinstance(ev, str):
        try:
            ev = json.loads(ev)
        except Exception:
            ev = {}
    return ev if isinstance(ev, dict) else {}


def _parse_advisor_raw(row: AdvisorRecommendation) -> dict:
    raw = row.raw_json
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _advisor_commitment_type(row: AdvisorRecommendation) -> str:
    raw = _parse_advisor_raw(row)
    props = raw.get("properties") or {}
    rec_type = str(props.get("recommendationTypeId") or props.get("recommendationType") or "").lower()
    text = f"{row.summary} {row.description or ''} {rec_type}".lower()
    if "savings" in rec_type or "savings plan" in text:
        return "savings_plan"
    return "reserved_instance"


def _is_reservation_advisor_row(row: AdvisorRecommendation) -> bool:
    if (row.category or "").lower() != "cost":
        return False
    raw = _parse_advisor_raw(row)
    props = raw.get("properties") or {}
    rec_type = str(props.get("recommendationTypeId") or props.get("recommendationType") or "")
    haystack = " ".join([
        row.summary or "",
        row.description or "",
        rec_type,
    ])
    return bool(_RESERVATION_KEYWORDS.search(haystack))


def _monthly_spend(db: Session, sub: str, month: str, *, service_pattern: str | None = None) -> tuple[float, str]:
    q = db.query(CostByServiceSnapshot).filter(
        CostByServiceSnapshot.subscription_id == sub,
        CostByServiceSnapshot.month == month,
    )
    rows = q.all()
    currency = "CAD"
    total = 0.0
    for r in rows:
        currency = r.billing_currency or currency
        if service_pattern and not re.search(service_pattern, r.service_name or "", re.I):
            continue
        total += float(r.cost_billing or 0)
    return round(total, 2), currency


def _finding_recommendation(f: OptimizationFinding, ev: dict) -> dict[str, Any]:
    savings = float(getattr(f, "estimated_savings_usd") or 0)
    commitment_type = ev.get("commitment_type") or (
        "reserved_instance" if "RESERVED" in (f.rule_id or "") else "savings_plan"
    )
    return {
        "id": f"finding:{f.id}",
        "source": "engine_finding",
        "commitment_type": commitment_type,
        "title": f.title or f.rule_id,
        "detail": f.detail,
        "recommendation": f.recommendation,
        "resource_id": f.resource_id,
        "severity": f.severity,
        "scope": ev.get("scope", "resource"),
        "estimated_monthly_savings": round(savings, 2),
        "estimated_annual_savings": round(savings * 12, 2),
        "running_vm_count": ev.get("running_vm_count"),
        "rule_id": f.rule_id,
    }


def _advisor_recommendation(row: AdvisorRecommendation) -> dict[str, Any]:
    monthly = float(row.potential_savings_monthly or 0)
    yearly = float(row.potential_savings_yearly or monthly * 12)
    if monthly <= 0 and yearly > 0:
        monthly = round(yearly / 12, 2)
    return {
        "id": f"advisor:{row.recommendation_id}",
        "source": "azure_advisor",
        "commitment_type": _advisor_commitment_type(row),
        "title": row.summary,
        "detail": row.description,
        "recommendation": row.description,
        "resource_id": row.resource_id,
        "severity": (row.impact or "Medium").lower(),
        "scope": "subscription" if not row.resource_id or "/providers/" not in row.resource_id else "resource",
        "estimated_monthly_savings": round(monthly, 2),
        "estimated_annual_savings": round(yearly if yearly else monthly * 12, 2),
        "impact": row.impact,
        "recommendation_id": row.recommendation_id,
    }


def _dedupe_by_id(items: list[dict[str, Any]], *, key: str = "id") -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        ident = str(item.get(key) or "")
        if not ident or ident in seen:
            continue
        seen.add(ident)
        out.append(item)
    return out


def _dedupe_recommendations(recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for rec in sorted(recs, key=lambda r: -(r.get("estimated_annual_savings") or 0)):
        key = rec.get("id") or ""
        if not key:
            fallback = "|".join([
                rec.get("source", ""),
                rec.get("title", ""),
                rec.get("resource_id", ""),
                rec.get("commitment_type", ""),
            ])
            key = fallback
        if key in seen:
            continue
        seen.add(key)
        out.append(rec)
    return out


def _underutilised_from_azure(commitments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in commitments:
        util = c.get("utilization_percent")
        if util is None or util >= _UNDERUTIL_THRESHOLD:
            continue
        out.append({
            "id": c.get("id"),
            "title": c.get("display_name") or c.get("name"),
            "resource_id": c.get("id"),
            "commitment_type": c.get("commitment_type"),
            "utilisation_pct": util,
            "wasted_usd": None,
            "source": c.get("source", "azure"),
            "severity": "high" if util < 50 else "medium",
        })
    return out


def build_reservation_advisor(
    db: Session,
    subscription_id: str,
    *,
    commitment_type: str = "all",
    month: str | None = None,
    headers: dict[str, str] | None = None,
    include_live_azure: bool = True,
) -> dict[str, Any]:
    """Unified reservation advisor payload for UI and exports."""
    sub = _normalize_sub(subscription_id)
    m = month or date.today().strftime("%Y-%m")
    warnings: list[str] = []
    sources = {"engine_findings": True, "azure_advisor_db": True, "azure_live": False}

    vm_spend, currency = _monthly_spend(db, sub, m, service_pattern=r"virtual machine|compute")
    compute_spend, _ = _monthly_spend(db, sub, m, service_pattern=r"virtual machine|compute|kubernetes|container")

    live = {"reservations": [], "savings_plans": [], "reservation_summaries": [], "savings_plan_summaries": []}
    if include_live_azure and headers:
        try:
            live = fetch_live_commitments(sub, headers)
            sources["azure_live"] = bool(
                live.get("reservations") or live.get("savings_plans") or live.get("reservation_summaries")
            )
        except Exception as exc:
            warnings.append(f"Azure live inventory: {str(exc)[:120]}")
            log.warning("reservation_advisor.live_failed", subscription_id=sub, error=str(exc)[:200])
    elif include_live_azure:
        warnings.append("Azure live inventory skipped — no ARM credentials in this request.")

    active_commitments = [*live.get("reservations", []), *live.get("savings_plans", [])]

    findings = (
        db.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == sub,
            OptimizationFinding.rule_id.in_(list(_RI_OPPORTUNITY_RULES | _RI_ACTIVE_RULES)),
        )
        .all()
    )

    engine_recs: list[dict[str, Any]] = []
    engine_underutil: list[dict[str, Any]] = []
    for f in findings:
        ev = _extract_evidence(f)
        if f.rule_id in _RI_OPPORTUNITY_RULES:
            engine_recs.append(_finding_recommendation(f, ev))
        elif f.rule_id in _RI_ACTIVE_RULES:
            engine_underutil.append({
                "id": f"finding:{f.id}",
                "title": f.title,
                "resource_id": f.resource_id,
                "commitment_type": "reserved_instance" if "RESERVED" in (f.rule_id or "") else "savings_plan",
                "utilisation_pct": ev.get("utilisation_pct"),
                "wasted_usd": float(getattr(f, "estimated_savings_usd") or 0),
                "source": "engine_finding",
                "severity": f.severity,
            })

    advisor_rows = (
        db.query(AdvisorRecommendation)
        .filter(
            AdvisorRecommendation.subscription_id == sub,
            AdvisorRecommendation.status == "Active",
        )
        .all()
    )
    advisor_recs = [_advisor_recommendation(r) for r in advisor_rows if _is_reservation_advisor_row(r)]

    all_recs = _dedupe_recommendations([*advisor_recs, *engine_recs])
    if commitment_type == "reserved_instance":
        all_recs = [r for r in all_recs if r.get("commitment_type") == "reserved_instance"]
    elif commitment_type == "savings_plan":
        all_recs = [r for r in all_recs if r.get("commitment_type") == "savings_plan"]

    underutilised = _dedupe_by_id([
        *engine_underutil,
        *_underutilised_from_azure(active_commitments),
    ])

    reserved_count = len(live.get("reservations") or [])
    sp_count = len(live.get("savings_plans") or [])
    monthly_opportunity = round(sum(r.get("estimated_monthly_savings") or 0 for r in all_recs), 2)
    annual_opportunity = round(sum(r.get("estimated_annual_savings") or 0 for r in all_recs), 2)

    if reserved_count + sp_count > 0 and compute_spend > 0:
        covered_estimate = min(compute_spend, compute_spend * 0.35 * reserved_count + compute_spend * 0.25 * sp_count)
        coverage_pct = round(min(100.0, 100.0 * covered_estimate / compute_spend), 1)
    elif reserved_count + sp_count > 0:
        coverage_pct = None
    else:
        coverage_pct = 0.0 if compute_spend > 0 else None

    if not advisor_recs and not engine_recs:
        warnings.append("No reservation or savings plan recommendations found. Sync Azure Advisor and run the optimization engine.")
    if not active_commitments and sources["azure_live"]:
        warnings.append("No active reservations or savings plans returned from Azure for this subscription.")

    return {
        "subscription_id": sub,
        "month": m,
        "billing_currency": currency,
        "commitment_type_filter": commitment_type,
        "sources": sources,
        "warnings": warnings,
        "summary": {
            "total_vm_spend_monthly": vm_spend,
            "total_compute_spend_monthly": compute_spend,
            "estimated_coverage_pct": coverage_pct,
            "active_reservations_count": reserved_count,
            "active_savings_plans_count": sp_count,
            "total_recommendations": len(all_recs),
            "total_monthly_opportunity": monthly_opportunity,
            "total_annual_opportunity": annual_opportunity,
            "underutilised_count": len(underutilised),
        },
        "active_commitments": active_commitments,
        "underutilised_commitments": underutilised[:50],
        "recommendations": all_recs[:75],
        "reservation_summaries": live.get("reservation_summaries") or [],
        "savings_plan_summaries": live.get("savings_plan_summaries") or [],
        # Backward-compatible fields
        "total_vm_spend": vm_spend,
        "estimated_coverage_pct": coverage_pct,
        "total_opportunity_savings_usd": monthly_opportunity,
        "commitment_opportunities": all_recs[:25],
        "total_recommendations": len(all_recs),
        "total_estimated_annual_savings_usd": annual_opportunity,
        "source": "merged",
    }


def sync_reservation_advisor(
    db: Session,
    subscription_id: str,
    token: str,
    *,
    trigger_advisor_generate: bool = False,
) -> dict[str, Any]:
    """Refresh Advisor snapshots then return unified advisor payload."""
    from app.advisor_sync import sync_azure_advisor_recommendations
    from app.auth import arm_auth_context

    sub = _normalize_sub(subscription_id)
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
            log.warning("reservation_advisor.advisor_sync_failed", error=str(exc)[:200])

        payload = build_reservation_advisor(
            db,
            sub,
            headers={"Authorization": f"Bearer {token}"},
            include_live_azure=True,
        )

    payload["sync"] = {
        "advisor": advisor_result,
        "status": "ok" if advisor_result.get("status") in {"ok", "partial", "skipped"} else "error",
    }
    return payload
