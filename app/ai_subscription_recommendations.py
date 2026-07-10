"""Subscription-level Azure OpenAI recommendations from stored optimization findings."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai_analysis import (
    _compact_finding,
    _load_ai_config,
    _parse_json_response,
)
from app.ai_subscription_context import enrich_subscription_context, filter_resolved_data_gaps
from app.ai_client import chat_completion
from app.models import OptimizationFinding

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """You are an Azure FinOps advisor. Analyze the subscription optimization data and produce prioritized, actionable recommendations.

Writing style:
- Evaluate objectively from the supplied data. Do NOT address the reader — no "you", "your", "please", or portal walkthroughs.
- executive_summary and recommendation: cite specific findings, metrics, or savings from the payload.
- implementation_steps: concise operational steps to execute each recommendation (imperative verbs) — not instructions to a person.

Rules:
- Base every recommendation ONLY on the supplied findings, advisor recommendations, and context. Do not invent resources, metrics, or savings.
- Synthesize cross-cutting themes (for example idle disks, underutilized VMs) rather than repeating each finding verbatim.
- Each recommendation must reference supporting finding rules, advisor items, and/or resource names from the input.
- When advisor and engine both flag the same resource, treat them as one opportunity — do NOT sum savings from both sources.
- Distinguish decommission (remove resource) from rightsize (SKU reduction). Decommission supersedes rightsize on the same resource.
- Use estimated_monthly_savings_usd only from unified_savings context or explicit per-signal amounts; never add overlapping advisor + engine savings.
- Flag data gaps only where the supplied context and findings still lack evidence.
- Use governance_impact, network_cost_analysis, and storage_cost_analysis when present — do not list those as data gaps.

Return JSON only:
{
  "executive_summary": "...",
  "total_estimated_monthly_savings_usd": 0,
  "quick_wins": ["..."],
  "data_gaps": ["..."],
  "recommendations": [
    {
      "priority": 1,
      "title": "...",
      "category": "compute|storage|network|kubernetes|database|security|cost|governance",
      "recommendation": "...",
      "rationale": "...",
      "estimated_monthly_savings_usd": null,
      "risk_level": "low|medium|high",
      "confidence": "high|medium|low",
      "implementation_steps": ["..."],
      "related_rule_ids": ["RULE_ID"],
      "related_resources": ["resource-name"]
    }
  ]
}
"""

_sub_ai_cache: dict[str, dict[str, Any]] = {}
_sub_ai_cache_lock = threading.Lock()

_VALID_CATEGORIES = {
    "compute", "storage", "network", "kubernetes", "database",
    "security", "cost", "governance",
}
_VALID_RISK = {"low", "medium", "high"}
_VALID_CONFIDENCE = {"high", "medium", "low"}


def clear_subscription_ai_cache() -> None:
    with _sub_ai_cache_lock:
        _sub_ai_cache.clear()


def _parse_evidence_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _finding_row_to_dict(row: OptimizationFinding) -> dict[str, Any]:
    from app.savings_aggregation import action_class_label, classify_engine_finding

    action_class = classify_engine_finding(row)
    return {
        "id": row.id,
        "rule_id": row.rule_id,
        "rule_name": row.rule_name,
        "category": row.category,
        "severity": row.severity,
        "resource_id": row.resource_id,
        "resource_name": row.resource_name,
        "resource_type": row.resource_type,
        "resource_group": row.resource_group,
        "detail": row.detail,
        "recommendation": row.recommendation,
        "estimated_savings_usd": row.estimated_savings_usd,
        "confidence_score": getattr(row, "confidence_score", None),
        "evidence": _parse_evidence_json(getattr(row, "evidence_json", None) or "{}"),
        "status": row.status,
        "source": "recommendation_engine",
        "action_class": action_class.value,
        "action_class_label": action_class_label(action_class),
    }


def _load_findings_for_ai(db: Session, subscription_id: str, *, limit: int) -> list[dict[str, Any]]:
    sub = subscription_id.strip().lower()
    rows = (
        db.query(OptimizationFinding)
        .filter(
            func.lower(OptimizationFinding.subscription_id) == sub,
            OptimizationFinding.status.in_(["open", "acknowledged"]),
        )
        .order_by(OptimizationFinding.estimated_savings_usd.desc().nullslast())
        .limit(max(limit * 3, limit))
        .all()
    )
    try:
        from app.analysis_persist import dedupe_open_findings_for_display
        rows = dedupe_open_findings_for_display(rows)
    except Exception:
        pass
    findings = [_finding_row_to_dict(row) for row in rows[:limit]]
    return sorted(
        findings,
        key=lambda f: float(f.get("estimated_savings_usd") or 0),
        reverse=True,
    )


def _load_advisor_for_ai(db: Session, subscription_id: str, *, limit: int = 40) -> list[dict[str, Any]]:
    from app.models import AdvisorRecommendation
    from app.savings_aggregation import classify_advisor_recommendation, action_class_label

    sub = subscription_id.strip().lower()
    rows = (
        db.query(AdvisorRecommendation)
        .filter(
            AdvisorRecommendation.subscription_id == sub,
            AdvisorRecommendation.status == "Active",
        )
        .order_by(AdvisorRecommendation.potential_savings_monthly.desc().nullslast())
        .limit(limit)
        .all()
    )
    items = []
    for row in rows:
        action_class = classify_advisor_recommendation(row)
        items.append({
            "id": row.id,
            "recommendation_id": row.recommendation_id,
            "category": row.category,
            "impact": row.impact,
            "summary": row.summary,
            "description": row.description,
            "resource_id": row.resource_id,
            "potential_savings_monthly": row.potential_savings_monthly,
            "action_class": action_class.value,
            "action_class_label": action_class_label(action_class),
            "source": "azure_advisor",
        })
    return items


def _subscription_context(db: Session, subscription_id: str) -> dict[str, Any]:
    from app.cost_db import subscription_mtd_from_sync_run
    from app.dashboard.api import get_advisor_findings_summary, get_findings_summary_db
    from app.savings_aggregation import aggregate_subscription_savings, action_class_label

    sub = subscription_id.strip().lower()
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    findings_summary = get_findings_summary_db(db, sub)
    advisor_summary = get_advisor_findings_summary(db, sub)
    unified = aggregate_subscription_savings(db, sub)
    mtd = subscription_mtd_from_sync_run(db, sub, month)

    by_category: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for key, value in (findings_summary.get("by_category") or {}).items():
        try:
            by_category[str(key).lower()] = int(value)
        except (TypeError, ValueError):
            continue
    for key, value in (findings_summary.get("by_severity") or {}).items():
        try:
            by_severity[str(key).lower()] = int(value)
        except (TypeError, ValueError):
            continue

    ctx: dict[str, Any] = {
        "month": month,
        "open_findings": int(findings_summary.get("open_count") or findings_summary.get("total") or 0),
        "findings_by_category": by_category,
        "findings_by_severity": by_severity,
        "advisor_active_count": int(advisor_summary.get("active_count") or 0),
        "advisor_high_impact_count": int(advisor_summary.get("high_impact") or 0),
        "unified_savings": unified,
        "unified_estimated_monthly_savings": unified.get("unified_estimated_monthly_savings"),
        "savings_by_action_class": {
            action_class_label(k): v for k, v in (unified.get("by_action_class") or {}).items()
        },
        "double_count_avoided_monthly": unified.get("double_count_avoided_monthly"),
        "resources_with_overlap": unified.get("resources_with_overlap"),
    }
    if mtd:
        ctx["mtd_spend"] = {
            "billing_currency": mtd.get("billing_currency") or "CAD",
            "pretax_total": mtd.get("pretax_total"),
            "synced_at": mtd.get("synced_at"),
        }
    return enrich_subscription_context(db, sub, ctx)


def _cache_key(subscription_id: str, findings: list[dict[str, Any]]) -> str:
    parts = [subscription_id.strip().lower()]
    for finding in findings:
        parts.append(
            "|".join([
                str(finding.get("id") or ""),
                str(finding.get("rule_id") or ""),
                str(finding.get("resource_id") or ""),
                json.dumps(finding.get("evidence") or {}, sort_keys=True, default=str),
            ]),
        )
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def _cache_get(key: str) -> dict[str, Any] | None:
    with _sub_ai_cache_lock:
        return _sub_ai_cache.get(key)


def _cache_set(key: str, value: dict[str, Any]) -> None:
    with _sub_ai_cache_lock:
        _sub_ai_cache[key] = value


def _normalize_recommendation(row: dict[str, Any], *, default_priority: int) -> dict[str, Any]:
    category = str(row.get("category") or "cost").strip().lower()
    if category not in _VALID_CATEGORIES:
        category = "cost"
    risk = str(row.get("risk_level") or "medium").strip().lower()
    if risk not in _VALID_RISK:
        risk = "medium"
    confidence = str(row.get("confidence") or "medium").strip().lower()
    if confidence not in _VALID_CONFIDENCE:
        confidence = "medium"
    try:
        priority = int(row.get("priority") or default_priority)
    except (TypeError, ValueError):
        priority = default_priority
    savings = row.get("estimated_monthly_savings_usd")
    try:
        savings = round(float(savings), 2) if savings not in (None, "") else None
    except (TypeError, ValueError):
        savings = None
    steps = row.get("implementation_steps") or []
    if not isinstance(steps, list):
        steps = [str(steps)]
    related_rules = row.get("related_rule_ids") or []
    if not isinstance(related_rules, list):
        related_rules = [str(related_rules)]
    related_resources = row.get("related_resources") or []
    if not isinstance(related_resources, list):
        related_resources = [str(related_resources)]
    return {
        "priority": priority,
        "title": str(row.get("title") or "Recommendation").strip(),
        "category": category,
        "recommendation": str(row.get("recommendation") or "").strip(),
        "rationale": str(row.get("rationale") or "").strip(),
        "estimated_monthly_savings_usd": savings,
        "risk_level": risk,
        "confidence": confidence,
        "implementation_steps": [str(s).strip() for s in steps if str(s).strip()],
        "related_rule_ids": [str(s).strip() for s in related_rules if str(s).strip()],
        "related_resources": [str(s).strip() for s in related_resources if str(s).strip()],
    }


def _normalize_ai_response(parsed: dict[str, Any], *, context: dict[str, Any] | None = None) -> dict[str, Any]:
    recommendations = []
    for idx, row in enumerate(parsed.get("recommendations") or []):
        if not isinstance(row, dict):
            continue
        normalized = _normalize_recommendation(row, default_priority=idx + 1)
        if normalized["recommendation"] or normalized["title"]:
            recommendations.append(normalized)
    recommendations.sort(key=lambda item: item["priority"])

    quick_wins = parsed.get("quick_wins") or []
    if not isinstance(quick_wins, list):
        quick_wins = [str(quick_wins)]
    data_gaps = parsed.get("data_gaps") or []
    if not isinstance(data_gaps, list):
        data_gaps = [str(data_gaps)]

    data_gaps = [str(item).strip() for item in data_gaps if str(item).strip()]
    if context:
        data_gaps = filter_resolved_data_gaps(data_gaps, context)

    total_savings = parsed.get("total_estimated_monthly_savings_usd")
    try:
        total_savings = round(float(total_savings), 2) if total_savings not in (None, "") else None
    except (TypeError, ValueError):
        total_savings = None
    if total_savings is None and recommendations:
        summed = sum(r["estimated_monthly_savings_usd"] or 0 for r in recommendations)
        total_savings = round(summed, 2) if summed > 0 else None

    return {
        "executive_summary": str(parsed.get("executive_summary") or "").strip(),
        "total_estimated_monthly_savings_usd": total_savings,
        "quick_wins": [str(item).strip() for item in quick_wins if str(item).strip()],
        "data_gaps": data_gaps,
        "recommendations": recommendations,
    }


def _compact_advisor_item(index: int, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": index,
        "source": "azure_advisor",
        "category": item.get("category"),
        "impact": item.get("impact"),
        "action_class": item.get("action_class"),
        "action_class_label": item.get("action_class_label"),
        "summary": item.get("summary"),
        "resource_id": item.get("resource_id"),
        "potential_savings_monthly": item.get("potential_savings_monthly"),
    }


def _call_subscription_ai(
    cfg: dict[str, Any],
    *,
    subscription_id: str,
    context: dict[str, Any],
    findings: list[dict[str, Any]],
    advisor_items: list[dict[str, Any]],
    db: Session | None,
) -> dict[str, Any] | None:
    compact_findings = [_compact_finding(i, finding) for i, finding in enumerate(findings)]
    compact_advisor = [_compact_advisor_item(i, item) for i, item in enumerate(advisor_items)]
    payload = {
        "subscription_id": subscription_id,
        "context": context,
        "findings": compact_findings,
        "advisor_recommendations": compact_advisor,
    }
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "Analyze this subscription and return prioritized recommendations:\n"
            + json.dumps(payload, separators=(",", ":"), default=str),
        },
    ]
    content = chat_completion(
        cfg,
        messages,
        max_tokens=min(6000, max(1200, 450 * max(len(findings), 1))),
        db=db,
    )
    if not content:
        return None
    parsed = _parse_json_response(content)
    if not parsed:
        return None
    return _normalize_ai_response(parsed, context=context)


def generate_subscription_ai_recommendations(
    db: Session,
    subscription_id: str,
    *,
    force_refresh: bool = False,
    max_findings: int | None = None,
) -> dict[str, Any]:
    """Run Azure OpenAI over stored findings and return synthesized recommendations."""
    sub = subscription_id.strip().lower()
    cfg = _load_ai_config(db)
    if not cfg:
        return {
            "subscription_id": sub,
            "ai_context": {
                "status": "not_configured",
                "message": "Configure Azure OpenAI in Settings to run AI analysis.",
            },
            "executive_summary": "",
            "total_estimated_monthly_savings_usd": None,
            "quick_wins": [],
            "data_gaps": [],
            "recommendations": [],
            "findings_analyzed": 0,
        }

    limit = max_findings if max_findings is not None else int(cfg.get("ai_max_findings_per_run") or 40)
    limit = max(1, min(200, limit))
    findings = _load_findings_for_ai(db, sub, limit=limit)
    advisor_items = _load_advisor_for_ai(db, sub, limit=min(limit, 40))
    if not findings and not advisor_items:
        return {
            "subscription_id": sub,
            "ai_context": {
                "status": "no_data",
                "message": "No open optimization findings or Advisor recommendations for this subscription. Run the engine and sync Advisor first.",
            },
            "executive_summary": "",
            "total_estimated_monthly_savings_usd": None,
            "quick_wins": [],
            "data_gaps": [],
            "recommendations": [],
            "findings_analyzed": 0,
        }

    cache_key = _cache_key(sub, findings)
    if not force_refresh:
        cached = _cache_get(cache_key)
        if cached:
            out = dict(cached)
            out["ai_context"] = {
                **(out.get("ai_context") or {}),
                "status": "cached",
                "cached": True,
            }
            return out

    context = _subscription_context(db, sub)
    parsed = _call_subscription_ai(
        cfg,
        subscription_id=sub,
        context=context,
        findings=findings,
        advisor_items=advisor_items,
        db=db,
    )
    if not parsed:
        return {
            "subscription_id": sub,
            "ai_context": {
                "status": "failed",
                "message": "AI request failed. Check Azure OpenAI settings and try again.",
                "deployment": cfg.get("openai_deployment"),
                "findings_analyzed": len(findings),
            },
            "executive_summary": "",
            "total_estimated_monthly_savings_usd": None,
            "quick_wins": [],
            "data_gaps": [],
            "recommendations": [],
            "findings_analyzed": len(findings),
        }

    billing_currency = (
        (context.get("mtd_spend") or {}).get("billing_currency")
        or "CAD"
    )
    result = {
        "subscription_id": sub,
        "billing_currency": billing_currency,
        "executive_summary": parsed["executive_summary"],
        "total_estimated_monthly_savings_usd": parsed["total_estimated_monthly_savings_usd"],
        "quick_wins": parsed["quick_wins"],
        "data_gaps": parsed["data_gaps"],
        "recommendations": parsed["recommendations"],
        "findings_analyzed": len(findings),
        "advisor_analyzed": len(advisor_items),
        "ai_context": {
            "status": "completed",
            "deployment": cfg.get("openai_deployment"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "findings_analyzed": len(findings),
            "advisor_analyzed": len(advisor_items),
            "cached": False,
        },
    }
    _cache_set(cache_key, result)
    log.info(
        "ai.subscription_recommendations_completed",
        subscription_id=sub,
        recommendations=len(parsed["recommendations"]),
        findings=len(findings),
    )
    return result
