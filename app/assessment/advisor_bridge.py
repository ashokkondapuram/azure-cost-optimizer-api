"""Merge Azure Advisor reliability/security findings into assessment evaluation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.focus_mapping import normalize_arm_id

# Pillars evaluated from assessment JSON (deterministic metrics + cost + governance).
JSON_EVALUATED_PILLARS = frozenset({"cost", "performance", "governance", "data", "operations", "metric"})

# Advisor categories merged as reliability/security findings at runtime.
ADVISOR_RELIABILITY_SECURITY_CATEGORIES = frozenset({
    "highavailability",
    "security",
    "operational excellence",  # legacy label
    "operationalexcellence",
})

ADVISOR_CATEGORY_TO_PILLAR: dict[str, str] = {
    "highavailability": "reliability",
    "security": "security",
    "operational excellence": "reliability",
    "operationalexcellence": "reliability",
}

_ADVISOR_IMPACT_TO_SEVERITY = {
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
}


def rule_pillar(rule: dict[str, Any]) -> str:
    return str(rule.get("pillar") or "").lower()


def is_json_evaluated_rule(rule: dict[str, Any]) -> bool:
    """True when a rule should be evaluated from assessment JSON (not Advisor)."""
    pillar = rule_pillar(rule)
    if pillar in {"reliability", "security"}:
        return False
    if pillar:
        return pillar in JSON_EVALUATED_PILLARS
    category = str(rule.get("category") or "").lower()
    if category in {"reliability", "security"}:
        return False
    # Unlabeled rules default to JSON evaluation (cost/performance analyzers).
    return True


def advisor_pillar_for_category(category: str | None) -> str | None:
    key = (category or "").strip().lower()
    if key in ADVISOR_CATEGORY_TO_PILLAR:
        return ADVISOR_CATEGORY_TO_PILLAR[key]
    if key == "highavailability":
        return "reliability"
    if key == "security":
        return "security"
    return None


def is_advisor_reliability_security_row(row: Any) -> bool:
    category = getattr(row, "category", None) or (row.get("category") if isinstance(row, dict) else None)
    key = str(category or "").strip().lower()
    return key in ADVISOR_RELIABILITY_SECURITY_CATEGORIES


def index_advisor_by_resource(db: Any, subscription_id: str) -> dict[str, list[Any]]:
    """Load active Advisor rows grouped by normalized ARM resource id."""
    from app.models import AdvisorRecommendation

    sub = subscription_id.strip().lower()
    rows = (
        db.query(AdvisorRecommendation)
        .filter(
            AdvisorRecommendation.subscription_id == sub,
            AdvisorRecommendation.status == "Active",
        )
        .all()
    )
    grouped: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        rid = normalize_arm_id(row.resource_id or "")
        if rid:
            grouped[rid].append(row)
    return dict(grouped)


def build_policy_from_advisor(rows: list[Any]) -> dict[str, Any]:
    """Derive assessment policy signals from Advisor reliability/security rows."""
    policy: dict[str, Any] = {
        "advisorRecommendationCount": len(rows),
    }
    any_high_rel = False
    any_high_sec = False
    any_critical_sec = False

    for row in rows:
        if not is_advisor_reliability_security_row(row):
            continue
        pillar = advisor_pillar_for_category(getattr(row, "category", None))
        impact = str(getattr(row, "impact", None) or "").strip().lower()
        if pillar == "reliability" and impact == "high":
            any_high_rel = True
        if pillar == "security":
            if impact == "high":
                any_high_sec = True
            if impact in {"high", "critical"}:
                any_critical_sec = any_critical_sec or impact == "critical"

    if any_high_rel:
        policy["anyHighReliabilityFinding"] = True
    if any_high_sec:
        policy["anyHighSecurityFinding"] = True
    if any_critical_sec:
        policy["anyCriticalSecurityFinding"] = True
    return policy


def _advisor_rule_id(row: Any) -> str:
    rec_id = str(getattr(row, "recommendation_id", None) or getattr(row, "recommendationId", None) or "")
    type_id = str(getattr(row, "recommendation_type_id", None) or "")
    if rec_id:
        return f"advisor_{rec_id}"
    if type_id:
        return f"advisor_{type_id}"
    return "advisor_recommendation"


def advisor_row_to_finding(
    row: Any,
    *,
    resource: dict[str, Any],
    subscription_id: str,
) -> dict[str, Any] | None:
    """Map one Advisor DB row to an OptimizationFinding-shaped dict."""
    if not is_advisor_reliability_security_row(row):
        return None

    pillar = advisor_pillar_for_category(getattr(row, "category", None))
    if not pillar:
        return None

    impact = str(getattr(row, "impact", None) or "Medium").strip().lower()
    severity = _ADVISOR_IMPACT_TO_SEVERITY.get(impact, "MEDIUM")
    summary = str(getattr(row, "summary", None) or "Advisor recommendation")
    description = str(getattr(row, "description", None) or summary)
    monthly = float(getattr(row, "potential_savings_monthly", None) or 0)

    resource_id = normalize_arm_id(
        getattr(row, "resource_id", None) or resource.get("resource_id") or resource.get("id") or ""
    )
    resource_block = resource.get("resource") or {}

    return {
        "rule_id": _advisor_rule_id(row),
        "rule_name": summary[:140],
        "category": pillar,
        "severity": severity,
        "resource_id": resource_id,
        "resource_name": resource.get("resource_name") or resource_block.get("name") or "",
        "resource_type": resource.get("resource_type") or resource_block.get("type") or "",
        "resource_group": resource.get("resource_group") or resource_block.get("resource_group") or "",
        "location": resource.get("location") or resource_block.get("location") or "",
        "detail": description or summary,
        "recommendation": description or summary,
        "estimated_savings_usd": monthly,
        "evidence": {
            "engine": "azure_advisor",
            "rule_source": "azure_advisor",
            "pillar": pillar,
            "advisor_recommendation_id": getattr(row, "recommendation_id", None),
            "advisor_category": getattr(row, "category", None),
            "advisor_impact": getattr(row, "impact", None),
        },
        "status": "open",
        "subscription_id": subscription_id,
    }


def advisor_rows_to_findings(
    rows: list[Any],
    *,
    resource: dict[str, Any],
    subscription_id: str,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        finding = advisor_row_to_finding(row, resource=resource, subscription_id=subscription_id)
        if not finding:
            continue
        rid = finding["rule_id"]
        if rid in seen:
            continue
        seen.add(rid)
        findings.append(finding)
    return findings


def filter_duplicate_advisor_findings(
    json_findings: list[dict[str, Any]],
    advisor_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop Advisor rows when an equivalent JSON rule already fired on the resource."""
    json_pillars = {
        str((f.get("evidence") or {}).get("pillar") or f.get("category") or "").lower()
        for f in json_findings
    }
    if not json_pillars:
        return advisor_findings

    filtered: list[dict[str, Any]] = []
    for finding in advisor_findings:
        pillar = str(finding.get("category") or "").lower()
        # JSON no longer emits reliability/security; only skip on explicit duplicate rule ids.
        if pillar in json_pillars.intersection({"reliability", "security"}):
            continue
        filtered.append(finding)
    return filtered
