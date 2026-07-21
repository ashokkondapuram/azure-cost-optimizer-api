"""Filter region-governance assessment rules and evidence metadata."""

from __future__ import annotations

from typing import Any

_REGION_GOVERNANCE_RULE_IDS = frozenset({
    "best_unapproved_region",
    "region_migration_required",
    "region_governance_review",
})

_INTERNAL_EVIDENCE_KEYS = frozenset({
    "engine",
    "rule_source",
    "sub_engine",
    "recommendation_action",
    "pillar",
    "confidence",
    "offer_type",
    "region_count",
    "resource_elements",
    "signals",
    "assessment_file",
    "required_evidence",
    "evidence_factors",
    "exclude_inventory_facts",
    "_evidence_meta",
    "rule_thresholds",
    "data_quality",
})


def region_governance_enabled(assessment: dict[str, Any] | None) -> bool:
    """True only when assessment JSON explicitly opts into region governance rules."""
    block = (assessment or {}).get("regionGovernance") or {}
    return bool(block.get("enabled"))


def is_region_governance_rule(rule: dict[str, Any] | None, *, rule_id: str = "") -> bool:
    rid = str(rule_id or (rule or {}).get("id") or (rule or {}).get("rule_id") or "").strip().lower()
    if not rid:
        return False
    if rid in _REGION_GOVERNANCE_RULE_IDS or "unapproved_region" in rid:
        return True
    pillar = str((rule or {}).get("pillar") or "").strip().lower()
    action = (
        (rule or {}).get("recommendationAction")
        or (rule or {}).get("actionOutcome")
        or ((rule or {}).get("output") or {}).get("recommendationAction")
        or ((rule or {}).get("recommendation") or {}).get("action")
        if isinstance((rule or {}).get("recommendation"), dict)
        else None
    )
    if pillar == "governance" and action == "migrate_region":
        return True
    return False


def is_region_governance_finding(finding: dict[str, Any] | None, evidence: dict[str, Any] | None = None) -> bool:
    if not finding and not evidence:
        return False
    rule_id = ""
    if isinstance(finding, dict):
        rule_id = str(finding.get("rule_id") or "")
    ev = evidence if isinstance(evidence, dict) else {}
    if not ev and isinstance(finding, dict):
        raw = finding.get("evidence")
        ev = raw if isinstance(raw, dict) else {}
    rid = rule_id or str(ev.get("rule_id") or "")
    if is_region_governance_rule({"id": rid}, rule_id=rid):
        return True
    if str(ev.get("recommendation_action") or "").strip().lower() == "migrate_region":
        return True
    if str(ev.get("pillar") or "").strip().lower() == "governance" and ev.get("engine") == "assessment_json":
        if "unapproved" in rid.lower() or "region" in rid.lower():
            return True
    return False


def strip_internal_evidence_keys(evidence: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        return {}
    return {key: value for key, value in evidence.items() if key not in _INTERNAL_EVIDENCE_KEYS}


def internal_evidence_keys() -> frozenset[str]:
    return _INTERNAL_EVIDENCE_KEYS
