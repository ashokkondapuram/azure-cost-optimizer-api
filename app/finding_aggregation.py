"""Group optimization findings by resource for Action centre display."""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from app.finding_dedupe import is_subscription_scoped_finding
from app.finding_taxonomy import sort_findings_by_priority
from app.focus_mapping import normalize_arm_id


def _field(finding: Any, name: str, default: Any = None) -> Any:
    if isinstance(finding, dict):
        return finding.get(name, default)
    return getattr(finding, name, default)


def _evidence_raw(finding: Any) -> Any:
    if isinstance(finding, dict):
        return finding.get("evidence") or finding.get("evidence_json")
    return getattr(finding, "evidence_json", None)


def resource_aggregation_key(finding: Any) -> str:
    """Stable key for grouping findings that belong to one Action centre row."""
    sub = str(_field(finding, "subscription_id") or "").strip().lower()
    rule_id = str(_field(finding, "rule_id") or "")
    if is_subscription_scoped_finding(rule_id=rule_id, evidence=_evidence_raw(finding)):
        return f"{sub}::subscription::{rule_id}"
    rid = normalize_arm_id(str(_field(finding, "resource_id") or ""))
    return f"{sub}::{rid}"


def finding_row_to_payload(finding: Any) -> dict[str, Any]:
    """Serialize an ORM row or API dict to a plain finding payload."""
    evidence = _evidence_raw(finding)
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence) if evidence.strip() else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            evidence = {}
    if not isinstance(evidence, dict):
        evidence = {}

    return {
        "id": _field(finding, "id"),
        "run_id": _field(finding, "run_id"),
        "rule_id": _field(finding, "rule_id"),
        "rule_name": _field(finding, "rule_name"),
        "category": _field(finding, "category"),
        "severity": _field(finding, "severity"),
        "resource_id": _field(finding, "resource_id"),
        "resource_name": _field(finding, "resource_name"),
        "resource_type": _field(finding, "resource_type"),
        "resource_group": _field(finding, "resource_group"),
        "location": _field(finding, "location"),
        "detail": _field(finding, "detail"),
        "recommendation": _field(finding, "recommendation"),
        "estimated_savings_usd": float(_field(finding, "estimated_savings_usd") or 0),
        "annualized_savings_usd": _field(finding, "annualized_savings_usd"),
        "waste_score": _field(finding, "waste_score"),
        "confidence_score": _field(finding, "confidence_score"),
        "action_priority": _field(finding, "action_priority"),
        "impact": _field(finding, "impact"),
        "evidence": evidence,
        "status": _field(finding, "status"),
        "detected_at": str(_field(finding, "detected_at") or ""),
        "resolved_at": str(_field(finding, "resolved_at")) if _field(finding, "resolved_at") else None,
        "chain_id": _field(finding, "chain_id"),
        "chain_step": _field(finding, "chain_step"),
        "chain_total": _field(finding, "chain_total"),
        "subscription_id": _field(finding, "subscription_id"),
    }


def serialize_child_recommendation(finding: Any) -> dict[str, Any]:
    """Compact recommendation payload nested under an aggregated finding."""
    payload = finding_row_to_payload(finding)
    return {
        "id": payload.get("id"),
        "rule_id": payload.get("rule_id"),
        "rule_name": payload.get("rule_name"),
        "category": payload.get("category"),
        "severity": payload.get("severity"),
        "detail": payload.get("detail"),
        "recommendation": payload.get("recommendation"),
        "estimated_savings_usd": payload.get("estimated_savings_usd"),
        "annualized_savings_usd": payload.get("annualized_savings_usd"),
        "waste_score": payload.get("waste_score"),
        "confidence_score": payload.get("confidence_score"),
        "action_priority": payload.get("action_priority"),
        "impact": payload.get("impact"),
        "evidence": payload.get("evidence"),
        "detected_at": payload.get("detected_at"),
        "status": payload.get("status"),
    }


def aggregate_findings_by_resource(findings: list[Any]) -> list[dict[str, Any]]:
    """Return one Action centre finding per resource with nested recommendations."""
    if not findings:
        return []

    grouped: dict[str, list[Any]] = defaultdict(list)
    for finding in findings:
        grouped[resource_aggregation_key(finding)].append(finding)

    aggregated: list[dict[str, Any]] = []
    for bucket in grouped.values():
        ordered = sort_findings_by_priority(bucket)
        primary = ordered[0]
        if len(ordered) == 1:
            aggregated.append(finding_row_to_payload(primary))
            continue

        total_savings = round(
            sum(float(_field(row, "estimated_savings_usd") or 0) for row in ordered),
            2,
        )
        total_waste = max(int(_field(row, "waste_score") or 0) for row in ordered)
        total_confidence = max(int(_field(row, "confidence_score") or 0) for row in ordered)
        child_payloads = [serialize_child_recommendation(row) for row in ordered]

        payload = finding_row_to_payload(primary)
        payload.update({
            "aggregated": True,
            "recommendation_count": len(ordered),
            "estimated_savings_usd": total_savings,
            "waste_score": total_waste,
            "confidence_score": total_confidence,
            "recommendations": child_payloads,
            "child_finding_ids": [row.get("id") for row in child_payloads if row.get("id")],
        })
        aggregated.append(payload)

    return sort_findings_by_priority(aggregated)
