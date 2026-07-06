"""Rank and filter optimization findings for actionable advanced analysis."""
from __future__ import annotations

import json
from typing import Any

from app.findings_summary import COST_OPTIMIZATION_RULE_IDS

# Re-export for callers that only need rule ids.
RIGHTSIZING_RULE_IDS = COST_OPTIMIZATION_RULE_IDS

_HIGH_SEVERITIES = frozenset({"CRITICAL", "HIGH"})
_SECURITY_CATEGORIES = frozenset({"SECURITY", "RELIABILITY"})
_LOW_VALUE_GOVERNANCE_RULES = frozenset({
    "VM_MISSING_GOVERNANCE_TAGS",
    "ASP_MISSING_TAGS_EXTENDED",
    "STORAGE_MISSING_TAGS_EXTENDED",
})

# Governance rules that remain high-signal even when estimated_savings_usd == 0.
# These are excluded from the blanket governance score penalty.
_IMPORTANT_GOVERNANCE_RULES = frozenset({
    "MISSING_COST_ALLOCATION_TAGS",
    "RESOURCE_MISSING_REQUIRED_TAGS",
    "SUBSCRIPTION_MISSING_BUDGET_ALERT",
    "RESOURCE_UNTAGGED_COST_CENTER",
})

# Named threshold constants — avoid magic-number coupling between callers.
FINDING_VALUE_MIN_SCORE: float = 48.0
# Shortcut threshold: findings above this savings+confidence bar are accepted
# even if their raw value score is slightly below FINDING_VALUE_MIN_SCORE.
FINDING_SAVINGS_SHORTCUT_THRESHOLD: float = FINDING_VALUE_MIN_SCORE - 5.0


def parse_finding_evidence(finding: Any) -> dict[str, Any]:
    """Return evidence dict from an ORM row or API payload."""
    raw = None
    if isinstance(finding, dict):
        raw = finding.get("evidence")
    else:
        raw = getattr(finding, "evidence_json", None)
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _field(finding: Any, name: str, default: Any = None) -> Any:
    if isinstance(finding, dict):
        return finding.get(name, default)
    return getattr(finding, name, default)


def _is_rightsizing_finding(finding: Any, evidence: dict[str, Any]) -> bool:
    rule_id = _field(finding, "rule_id") or ""
    if rule_id in RIGHTSIZING_RULE_IDS:
        return True
    action = evidence.get("sizing_action")
    return action in {"downgrade", "cross_family", "upgrade"}


def finding_value_score(finding: Any, *, _evidence: dict[str, Any] | None = None) -> float:
    """Higher scores indicate findings worth surfacing in advanced analysis.

    Pass a pre-parsed ``_evidence`` dict to avoid redundant json.loads calls
    when both this function and the caller already have evidence available.
    """
    savings = float(_field(finding, "estimated_savings_usd") or 0)
    confidence = int(_field(finding, "confidence_score") or 0)
    waste = int(_field(finding, "waste_score") or 0)
    severity = str(_field(finding, "severity") or "").upper()
    category = str(_field(finding, "category") or "").upper()
    rule_id = str(_field(finding, "rule_id") or "")
    evidence = _evidence if _evidence is not None else parse_finding_evidence(finding)
    data_quality = str(evidence.get("data_quality") or "")

    score = 0.0
    score += min(max(savings, 0.0), 500.0) * 0.12
    score += confidence * 0.30
    score += waste * 0.22

    if severity in _HIGH_SEVERITIES:
        score += 12.0
    elif severity == "MEDIUM":
        score += 4.0

    if savings >= 50:
        score += 10.0
    elif savings >= 15:
        score += 5.0

    if _is_rightsizing_finding(finding, evidence):
        score += 18.0
        if data_quality == "full_monitor":
            score += 12.0

    if evidence.get("pricing_status") == "available" or evidence.get("pricing_source") == "azure_retail_prices":
        score += 8.0

    if category in _SECURITY_CATEGORIES and confidence >= 70:
        score += 10.0

    if rule_id in _LOW_VALUE_GOVERNANCE_RULES:
        score -= 35.0
    elif (
        category == "GOVERNANCE"
        and savings <= 0
        and severity in {"LOW", "INFO"}
        and rule_id not in _IMPORTANT_GOVERNANCE_RULES
    ):
        # Only penalise low-signal governance findings; preserve high-signal ones.
        score -= 28.0

    if severity == "INFO":
        score -= 22.0
    if data_quality == "inventory_only" and confidence < 55 and savings < 20:
        score -= 30.0
    if data_quality == "partial_monitor" and confidence < 50 and not _is_rightsizing_finding(finding, evidence):
        score -= 15.0

    return max(0.0, round(score, 2))


def is_valuable_finding(
    finding: Any,
    *,
    min_score: float = FINDING_VALUE_MIN_SCORE,
    _evidence: dict[str, Any] | None = None,
) -> bool:
    """True when a finding is actionable enough for advanced analysis.

    Pass a pre-parsed ``_evidence`` dict to avoid redundant json.loads calls.
    """
    savings = float(_field(finding, "estimated_savings_usd") or 0)
    confidence = int(_field(finding, "confidence_score") or 0)
    waste = int(_field(finding, "waste_score") or 0)
    severity = str(_field(finding, "severity") or "").upper()
    category = str(_field(finding, "category") or "").upper()
    rule_id = str(_field(finding, "rule_id") or "")
    # Parse once and reuse for both the shortcut checks and finding_value_score.
    evidence = _evidence if _evidence is not None else parse_finding_evidence(finding)

    if rule_id in _LOW_VALUE_GOVERNANCE_RULES and savings <= 0:
        return False
    if severity == "INFO" and savings <= 0 and category == "GOVERNANCE":
        return False
    if (
        savings >= 15.0
        and confidence >= 55
        and finding_value_score(finding, _evidence=evidence) >= FINDING_SAVINGS_SHORTCUT_THRESHOLD
    ):
        return True
    if _is_rightsizing_finding(finding, evidence) and evidence.get("data_quality") == "full_monitor":
        return True
    if category in _SECURITY_CATEGORIES and severity in _HIGH_SEVERITIES and confidence >= 65:
        return True
    if savings >= 50.0 and confidence >= 45:
        return True
    if waste >= 70 and confidence >= 75:
        return True
    return finding_value_score(finding, _evidence=evidence) >= min_score


def filter_valuable_findings(
    findings: list[Any],
    *,
    limit: int = 5,
    min_score: float = FINDING_VALUE_MIN_SCORE,
) -> list[Any]:
    """Return the highest-value findings for advanced analysis."""
    # Parse evidence once per finding to avoid repeated json.loads in the
    # is_valuable_finding / finding_value_score call chain.
    scored: list[tuple[Any, dict[str, Any], float]] = []
    for f in findings:
        ev = parse_finding_evidence(f)
        if not is_valuable_finding(f, min_score=min_score, _evidence=ev):
            continue
        score = finding_value_score(f, _evidence=ev)
        scored.append((f, ev, score))

    ranked = sorted(
        scored,
        key=lambda t: (
            -t[2],
            -float(_field(t[0], "estimated_savings_usd") or 0),
            -int(_field(t[0], "confidence_score") or 0),
        ),
    )
    return [f for f, _ev, _sc in ranked[: max(1, limit)]] if ranked else []


def serialize_finding_summary(finding: Any) -> dict[str, Any]:
    """Compact finding payload for advanced analysis surfaces."""
    evidence = parse_finding_evidence(finding)
    return {
        "id": _field(finding, "id"),
        "rule_id": _field(finding, "rule_id"),
        "rule_name": _field(finding, "rule_name"),
        "category": _field(finding, "category"),
        "severity": _field(finding, "severity"),
        "detail": _field(finding, "detail"),
        "recommendation": _field(finding, "recommendation"),
        "estimated_savings_usd": float(_field(finding, "estimated_savings_usd") or 0),
        "confidence_score": int(_field(finding, "confidence_score") or 0),
        "waste_score": int(_field(finding, "waste_score") or 0),
        "action_priority": _field(finding, "action_priority"),
        "impact": _field(finding, "impact"),
        "value_score": finding_value_score(finding, _evidence=evidence),
        "data_quality": evidence.get("data_quality"),
        "pricing_backed": (
            evidence.get("pricing_status") == "available"
            or evidence.get("pricing_source") == "azure_retail_prices"
        ),
    }
