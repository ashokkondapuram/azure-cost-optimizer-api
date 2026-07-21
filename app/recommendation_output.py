"""Validate and normalize optimization recommendation payloads for API persistence."""

from __future__ import annotations

import json
from typing import Any

from app.finding_dedupe import is_subscription_scoped_finding

GENERIC_PLACEHOLDER_RULE_IDS = frozenset({
    "",
    "assessment_rule",
    "unknown",
})

REQUIRED_API_FIELDS = (
    "rule_id",
    "severity",
    "resource_id",
    "detail",
    "recommendation",
    "estimated_savings_usd",
    "evidence",
)

_VALID_SEVERITIES = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"})


def _coerce_evidence(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _has_rule_provenance(rule_id: str, evidence: dict[str, Any]) -> bool:
    if evidence.get("rule_source") or evidence.get("engine"):
        return True
    if evidence.get("assessment_file"):
        return True
    if evidence.get("pricing_source") or evidence.get("pricing_status"):
        return True
    if rule_id.startswith("advisor_"):
        return True
    # Python engine findings include rule_id in evidence via build_rule_evidence.
    if evidence.get("rule_id") == rule_id:
        return True
    return False


def is_actionable_recommendation(finding: dict[str, Any]) -> bool:
    """True when a finding is a real rule-based recommendation (not a generic placeholder)."""
    if not isinstance(finding, dict):
        return False

    rule_id = str(finding.get("rule_id") or "").strip()
    if not rule_id or rule_id in GENERIC_PLACEHOLDER_RULE_IDS:
        return False
    if rule_id.startswith("metric_") and "_missing" in rule_id:
        return False

    severity = str(finding.get("severity") or "").strip().upper()
    if severity not in _VALID_SEVERITIES:
        return False

    resource_id = str(finding.get("resource_id") or "").strip()
    scoped = is_subscription_scoped_finding(rule_id=rule_id, evidence=finding.get("evidence"))
    if not resource_id and not scoped:
        return False

    detail = str(finding.get("detail") or "").strip()
    recommendation = str(finding.get("recommendation") or "").strip()
    if not detail and not recommendation:
        return False

    evidence = _coerce_evidence(finding.get("evidence"))
    if not _has_rule_provenance(rule_id, evidence):
        return False

    return True


def normalize_recommendation_finding(finding: dict[str, Any]) -> dict[str, Any] | None:
    """Return a normalized finding dict, or None when the row is not actionable."""
    if not is_actionable_recommendation(finding):
        return None

    out = dict(finding)
    out["rule_id"] = str(finding.get("rule_id") or "").strip()
    out["severity"] = str(finding.get("severity") or "MEDIUM").strip().upper()
    out["resource_id"] = str(finding.get("resource_id") or "").strip()
    out["detail"] = str(finding.get("detail") or finding.get("recommendation") or "").strip()
    out["recommendation"] = str(
        finding.get("recommendation") or finding.get("detail") or ""
    ).strip()
    try:
        out["estimated_savings_usd"] = round(float(finding.get("estimated_savings_usd") or 0), 2)
    except (TypeError, ValueError):
        out["estimated_savings_usd"] = 0.0
    out["evidence"] = _coerce_evidence(finding.get("evidence"))
    out["evidence"].setdefault("rule_source", out["evidence"].get("engine") or "rule_engine")
    return out


def filter_valid_recommendations(findings: list[Any]) -> list[dict[str, Any]]:
    """Drop placeholder or structurally invalid recommendations."""
    valid: list[dict[str, Any]] = []
    for row in findings or []:
        if hasattr(row, "to_dict"):
            row = row.to_dict()
        if not isinstance(row, dict):
            continue
        normalized = normalize_recommendation_finding(row)
        if normalized is not None:
            valid.append(normalized)
    return valid


_ACTION_TYPE_VERBS: dict[str, str] = {
    "resize_down": "Resize",
    "downgrade_disk": "Downgrade disk tier",
    "decommission": "Decommission",
    "buy_reservation": "Purchase reservation",
    "investigate": "Investigate",
    "manual_review": "Review manually",
}


def _parse_evidence_blob(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    return {}


def _format_savings_phrase(value: float | None) -> str | None:
    if value is None:
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    if amount <= 0:
        return None
    return f"${amount:,.0f}/mo estimated savings"


def _display_value(raw: Any, formatted: Any = None, *, key: str = "") -> str | None:
    if formatted not in (None, "", "—"):
        return str(formatted)
    if raw is None or raw == "" or raw == "—":
        return None
    if isinstance(raw, (int, float)):
        if key.endswith("_pct") or key.endswith("_percent"):
            return f"{float(raw):.1f}%"
        if isinstance(raw, float) and raw != int(raw):
            return f"{float(raw):,.1f}"
        return f"{int(raw):,}"
    return str(raw)


def _highlight_key(label: str, value: str) -> str:
    return f"{label.strip().lower()}:{value.strip().lower()}"


def extract_evidence_highlights(evidence: dict[str, Any], *, limit: int = 6) -> list[dict[str, str]]:
    """Pull measurable label/value pairs from enriched finding evidence."""
    highlights: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(label: str, value: str | None) -> None:
        if not label or not value or value in ("—", "N/A", "n/a"):
            return
        key = _highlight_key(label, value)
        if key in seen:
            return
        seen.add(key)
        highlights.append({"label": label.strip(), "value": value.strip()})

    for check in evidence.get("checks") or []:
        if not isinstance(check, dict):
            continue
        label = str(check.get("signal") or "").strip()
        value = _display_value(check.get("value"), check.get("value_display"))
        threshold = check.get("threshold_display") or check.get("threshold")
        if value and threshold and str(threshold) not in ("—", "", "N/A"):
            _add(label, f"{value} (threshold: {threshold})")
        elif value:
            _add(label, value)

    om = evidence.get("optimization_metrics") or {}
    for metric in (om.get("performance") or [])[:4]:
        if not isinstance(metric, dict):
            continue
        label = str(metric.get("label") or metric.get("id") or "").strip()
        formatted = metric.get("formatted")
        if formatted:
            _add(label, str(formatted))

    details = evidence.get("resource_details") or {}
    for key, label in (
        ("vm_size", "Current SKU"),
        ("suggested_sku", "Target SKU"),
        ("sku", "Disk SKU"),
        ("size_gb", "Disk size"),
        ("disk_iops_utilization_pct", "IOPS utilization"),
        ("avg_cpu_pct", "Average CPU"),
        ("avg_memory_pct", "Average memory"),
        ("provisioned_iops", "Provisioned IOPS"),
        ("measured_iops", "Measured IOPS"),
    ):
        raw = evidence.get(key) if evidence.get(key) is not None else details.get(key)
        value = _display_value(raw, key=key)
        if value:
            _add(label, value)

    return highlights[:limit]


def extract_target_action(
    evidence: dict[str, Any],
    recommendation: str = "",
    *,
    action_type: str | None = None,
) -> str | None:
    """Derive a concrete remediation step from evidence signals (no invented values)."""
    details = evidence.get("resource_details") or {}

    current_sku = evidence.get("vm_size") or details.get("vm_size")
    target_sku = evidence.get("suggested_sku") or evidence.get("target_sku")
    if current_sku and target_sku and str(current_sku) != str(target_sku):
        verb = _ACTION_TYPE_VERBS.get(action_type or "", "Resize")
        return f"{verb} from {current_sku} to {target_sku}"

    current_tier = evidence.get("sku") or details.get("sku")
    target_tier = evidence.get("target_tier") or evidence.get("suggested_tier")
    if current_tier and target_tier and str(current_tier) != str(target_tier):
        return f"Change disk tier from {current_tier} to {target_tier}"

    sizing_action = evidence.get("sizing_action")
    if sizing_action and target_sku:
        return f"{str(sizing_action).replace('_', ' ').title()} to {target_sku}"

    rec = (recommendation or "").strip()
    if rec and ("→" in rec or " to " in rec.lower()):
        first_sentence = rec.split(".")[0].strip()
        if len(first_sentence) >= 12:
            return first_sentence

    return None


def enrich_recommendation_narrative(
    finding: dict[str, Any],
    *,
    action_type: str | None = None,
    estimated_savings: float | None = None,
) -> dict[str, Any]:
    """Build concrete narrative text and metric highlights from finding evidence."""
    evidence = _parse_evidence_blob(finding.get("evidence"))
    detail = str(finding.get("detail") or "").strip()
    recommendation = str(finding.get("recommendation") or "").strip()
    summary = str(evidence.get("summary") or "").strip()

    savings = estimated_savings
    if savings is None:
        try:
            savings = float(finding.get("estimated_savings_usd") or 0) or None
        except (TypeError, ValueError):
            savings = None

    highlights = extract_evidence_highlights(evidence)
    target_action = extract_target_action(evidence, recommendation, action_type=action_type)
    savings_phrase = _format_savings_phrase(savings)
    has_evidence_signals = bool(summary or highlights or target_action)

    parts: list[str] = []
    if summary:
        parts.append(summary)
    elif detail and has_evidence_signals:
        parts.append(detail)

    if target_action and (not parts or target_action not in parts[0]):
        parts.append(target_action)
    elif recommendation and not summary and recommendation != detail and has_evidence_signals:
        parts.append(recommendation)

    narrative = ". ".join(p for p in parts if p)
    if savings_phrase and has_evidence_signals:
        narrative = f"{narrative}. {savings_phrase}" if narrative else savings_phrase

    return {
        "narrative": narrative,
        "action_text": target_action or recommendation or detail,
        "highlights": highlights,
        "savings_phrase": savings_phrase,
    }


def synthesize_action_narrative(
    findings: list[dict[str, Any]],
    *,
    action_type: str | None = None,
    estimated_savings: float | None = None,
    workload_type: str | None = None,
    recommendation_tier: str | None = None,
    fallback_reason: str = "",
) -> dict[str, Any]:
    """Merge finding evidence into a concrete proposed-action narrative."""
    if not findings:
        return {
            "narrative": fallback_reason,
            "action_text": None,
            "highlights": [],
            "savings_phrase": _format_savings_phrase(estimated_savings),
        }

    ordered = sorted(
        findings,
        key=lambda f: float(f.get("estimated_savings_usd") or 0),
        reverse=True,
    )
    primary = enrich_recommendation_narrative(
        ordered[0],
        action_type=action_type,
        estimated_savings=estimated_savings,
    )

    merged_highlights: list[dict[str, str]] = []
    seen: set[str] = set()
    for finding in ordered:
        ev = _parse_evidence_blob(finding.get("evidence"))
        for item in extract_evidence_highlights(ev):
            key = _highlight_key(item["label"], item["value"])
            if key not in seen:
                seen.add(key)
                merged_highlights.append(item)
    merged_highlights = merged_highlights[:8]

    narrative = primary.get("narrative") or fallback_reason
    if len(ordered) > 1:
        extra_rules = [
            str(f.get("rule_name") or f.get("rule_id") or "").strip()
            for f in ordered[1:3]
            if str(f.get("rule_name") or f.get("rule_id") or "").strip()
        ]
        if extra_rules:
            narrative = f"{narrative} Also flagged: {', '.join(extra_rules)}."

    if workload_type and action_type in {"resize_down", "buy_reservation"}:
        if workload_type.lower() not in narrative.lower():
            narrative = f"{narrative} ({workload_type} workload)"

    if recommendation_tier == "tier3_risky" and action_type != "manual_review":
        narrative = f"{narrative}. Higher risk — validate in non-production first"

    return {
        "narrative": narrative.strip(),
        "action_text": primary.get("action_text"),
        "highlights": merged_highlights,
        "savings_phrase": primary.get("savings_phrase") or _format_savings_phrase(estimated_savings),
    }


def recommendation_api_shape(finding: dict[str, Any]) -> dict[str, Any]:
    """Compact example-shaped payload for API responses and tests."""
    normalized = normalize_recommendation_finding(finding)
    if normalized is None:
        raise ValueError("finding is not an actionable recommendation")
    evidence = normalized.get("evidence") or {}
    return {
        "rule_id": normalized["rule_id"],
        "severity": normalized["severity"],
        "resource_id": normalized["resource_id"],
        "estimated_savings_usd": normalized["estimated_savings_usd"],
        "detail": normalized["detail"],
        "recommendation": normalized["recommendation"],
        "evidence": {
            "rule_source": evidence.get("rule_source") or evidence.get("engine"),
            "pillar": evidence.get("pillar"),
            "confidence": evidence.get("confidence"),
            "signals": evidence.get("signals") or {},
            "assessment_file": evidence.get("assessment_file"),
        },
    }
