"""Pick a single best Cosmos DB recommendation per account.

Cosmos rules can overlap (serverless vs autoscale vs manual downsize, throttling vs
downsize). This module suppresses conflicting paths and returns one primary finding
with an optional what-if scenario for the chosen action only.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.assessment.catalog import get_assessment_for_arm_type
from app.assessment.what_if import lookup_what_if_scenario
from app.focus_mapping import normalize_arm_id
from app.optimizer.core.finding import ExtendedFinding

_COSMOS_ARM_TYPE = "Microsoft.DocumentDB/databaseAccounts"

# Python extended-engine rule → assessment JSON rule (for what-if lookup).
PYTHON_TO_ASSESSMENT_RULE: dict[str, str] = {
    "COSMOS_SERVERLESS": "cosmos_serverless_candidate",
    "COSMOS_AUTOSCALE_EXTENDED": "cosmos_autoscale_candidate",
    "COSMOS_RU_RIGHT_SIZING_UNDER": "cosmos_rightsize_manual_throughput_down",
    "COSMOS_RU_RIGHT_SIZING_OVER": "cosmos_increase_throughput_or_fix_hot_partition",
    "COSMOS_THROTTLING_DETECTED": "cosmos_increase_throughput_or_fix_hot_partition",
    "COSMOS_HOT_CONTAINER_DETECTED": "cosmos_hot_partition",
    "COSMOS_INDEXING_OVERPROVISIONED": "cosmos_indexing_policy_optimization",
    "COSMOS_LARGE_ITEMS_DETECTED": "cosmos_ttl_for_stale_data",
    "COSMOS_CONSISTENCY_OVERPROVISIONED": "cosmos_consistency_cost_latency_review",
    "COSMOS_MULTI_WRITE_UNNECESSARY": "cosmos_multi_write_review",
    "COSMOS_FAILOVER_UNNECESSARY": "cosmos_automatic_failover",
    "COSMOS_API_COST_VARIANCE": "cosmos_consistency_cost_latency_review",
    "COSMOS_RESERVED_CAPACITY_ELIGIBLE": "cosmos_reserved_capacity",
}

THROUGHPUT_DOWN_RULES = frozenset({
    "COSMOS_SERVERLESS",
    "COSMOS_AUTOSCALE_EXTENDED",
    "COSMOS_RU_RIGHT_SIZING_UNDER",
    "COSMOS_PROVISIONED_EXTENDED",
    "cosmos_serverless_candidate",
    "cosmos_autoscale_candidate",
    "cosmos_rightsize_manual_throughput_down",
    "cosmos_autoscale_max_too_high",
})

CAPACITY_INCREASE_RULES = frozenset({
    "COSMOS_RU_RIGHT_SIZING_OVER",
    "COSMOS_THROTTLING_DETECTED",
    "cosmos_increase_throughput_or_fix_hot_partition",
    "cosmos_autoscale_max_too_low",
})

HOT_PARTITION_RULES = frozenset({
    "COSMOS_HOT_CONTAINER_DETECTED",
    "cosmos_hot_partition",
})

SEVERITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}

# Operational issues outrank cost-only optimizations.
RULE_PRIORITY = {
    "COSMOS_HOT_CONTAINER_DETECTED": 100,
    "cosmos_hot_partition": 100,
    "COSMOS_THROTTLING_DETECTED": 95,
    "COSMOS_RU_RIGHT_SIZING_OVER": 90,
    "cosmos_increase_throughput_or_fix_hot_partition": 90,
    "cosmos_autoscale_max_too_low": 85,
}


def _rule_key(rule_id: str | None) -> str:
    return (rule_id or "").strip()


def _finding_savings(finding: ExtendedFinding) -> float:
    try:
        return float(finding.estimated_savings_usd or 0)
    except (TypeError, ValueError):
        return 0.0


def _finding_score(finding: ExtendedFinding) -> tuple[int, int, float]:
    rule = _rule_key(finding.rule_id)
    priority = RULE_PRIORITY.get(rule, 0)
    sev = SEVERITY_RANK.get(str(finding.severity or "MEDIUM").upper(), 2)
    return (priority, sev, _finding_savings(finding))


def _suppress_conflicting(findings: list[ExtendedFinding]) -> list[ExtendedFinding]:
    """Remove mutually exclusive Cosmos recommendations before picking the winner."""
    if len(findings) <= 1:
        return findings

    present = {_rule_key(f.rule_id) for f in findings}
    suppressed: set[str] = set()

    has_hot = bool(present & HOT_PARTITION_RULES)
    has_throttle = bool(present & {"COSMOS_THROTTLING_DETECTED", "COSMOS_RU_RIGHT_SIZING_OVER"})
    has_capacity_stress = bool(present & CAPACITY_INCREASE_RULES)

    if has_hot or has_throttle or has_capacity_stress:
        suppressed |= THROUGHPUT_DOWN_RULES

    if has_hot:
        suppressed |= {
            "COSMOS_RU_RIGHT_SIZING_OVER",
            "COSMOS_THROTTLING_DETECTED",
            "cosmos_increase_throughput_or_fix_hot_partition",
        }

    throughput_candidates = [
        f for f in findings if _rule_key(f.rule_id) in THROUGHPUT_DOWN_RULES
    ]
    if len(throughput_candidates) > 1:
        best = max(throughput_candidates, key=_finding_score)
        for candidate in throughput_candidates:
            if candidate is not best:
                suppressed.add(_rule_key(candidate.rule_id))

    eligible = [f for f in findings if _rule_key(f.rule_id) not in suppressed]
    return eligible or findings


def pick_primary_cosmos_finding(findings: list[ExtendedFinding]) -> ExtendedFinding | None:
    """Return the single best Cosmos finding from a list for one resource."""
    if not findings:
        return None
    if len(findings) == 1:
        return findings[0]
    eligible = _suppress_conflicting(findings)
    return max(eligible, key=_finding_score)


def select_primary_cosmos_findings(findings: list[ExtendedFinding]) -> list[ExtendedFinding]:
    """One primary recommendation per Cosmos account."""
    by_resource: dict[str, list[ExtendedFinding]] = defaultdict(list)
    for finding in findings:
        rid = normalize_arm_id(finding.resource_id or "")
        if not rid:
            continue
        by_resource[rid].append(finding)

    primary: list[ExtendedFinding] = []
    for group in by_resource.values():
        winner = pick_primary_cosmos_finding(group)
        if winner is not None:
            primary.append(winner)
    return primary


def _assessment_rule(assessment: dict[str, Any], rule_id: str) -> dict[str, Any] | None:
    rid = (rule_id or "").upper()
    for rule in assessment.get("rules") or []:
        if str(rule.get("rule_id") or "").upper() == rid:
            out = dict(rule)
            out["id"] = rid
            rec = out.get("recommendation")
            if isinstance(rec, dict):
                out["recommendation"] = str(rec.get("action") or "")
                category = str(out.get("category") or "")
                if category == "performance" and "increase" in str(rec.get("action") or "").lower():
                    out["recommendationAction"] = "upgrade"
                elif category == "cost" and rule_id not in {
                    "COSMOS_PROVISIONED_EXTENDED",
                    "COSMOS_FAILOVER_UNNECESSARY",
                    "COSMOS_THROTTLING_DETECTED",
                    "COSMOS_RU_RIGHT_SIZING_OVER",
                    "COSMOS_HOT_CONTAINER_DETECTED",
                }:
                    out["recommendationAction"] = "downgrade"
                else:
                    out["recommendationAction"] = "investigate"
            return out
    for rule in assessment.get("recommendationRules") or []:
        if rule.get("id") == rule_id:
            return rule
    for rule in assessment.get("assessmentRules") or []:
        if rule.get("id") == rule_id:
            return rule
    return None


def enrich_primary_cosmos_what_if(findings: list[ExtendedFinding]) -> list[ExtendedFinding]:
    """Attach what-if only to the primary Cosmos recommendation."""
    assessment = get_assessment_for_arm_type(_COSMOS_ARM_TYPE)
    if not assessment:
        return findings

    for finding in findings:
        assessment_rule_id = PYTHON_TO_ASSESSMENT_RULE.get(
            _rule_key(finding.rule_id),
            _rule_key(finding.rule_id),
        )
        rule = _assessment_rule(assessment, assessment_rule_id)
        scenario = lookup_what_if_scenario(assessment, assessment_rule_id, rule=rule)
        evidence = dict(finding.evidence or {})
        evidence["primary_recommendation"] = True
        if scenario:
            evidence["what_if"] = scenario
        else:
            evidence.pop("what_if", None)
        finding.evidence = evidence
    return findings


def consolidate_cosmos_findings(findings: list[ExtendedFinding]) -> list[ExtendedFinding]:
    """Public entry: primary pick + what-if for Cosmos accounts."""
    primary = select_primary_cosmos_findings(findings)
    return enrich_primary_cosmos_what_if(primary)
