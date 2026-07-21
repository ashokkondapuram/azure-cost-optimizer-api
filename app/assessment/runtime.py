"""Deterministic assessment rule evaluation (DB-backed, no live Azure calls)."""

from __future__ import annotations

import re
from typing import Any

from app.assessment.advisor_bridge import is_json_evaluated_rule

_AZURE_OPTIMIZATION_PREFIX = re.compile(
    r"^Azure [^:]+ Production Optimization:\s*",
    re.IGNORECASE,
)


def get_path(data: dict[str, Any] | None, path: str) -> Any:
    if not data or not path:
        return None
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _condition_field(condition: dict[str, Any]) -> str | None:
    field = condition.get("field") or condition.get("path")
    if field:
        return str(field)
    return None


def evaluate_condition(resource: dict[str, Any], condition: dict[str, Any]) -> bool:
    field = _condition_field(condition)
    if not field:
        return False
    value = get_path(resource, field)
    if value is None and condition.get("missingData") == "rule_not_applicable":
        return False
    operator = condition.get("operator")
    expected = condition.get("value")

    if operator == "eq":
        return value == expected
    if operator == "neq":
        return value != expected
    if operator == "gt":
        return value is not None and value > expected
    if operator == "gte":
        return value is not None and value >= expected
    if operator == "lt":
        return value is not None and value < expected
    if operator == "lte":
        return value is not None and value <= expected
    if operator == "in":
        return value in (expected or [])
    if operator == "not_in":
        return value not in (expected or [])
    if operator == "contains":
        return value is not None and expected in value
    if operator == "missing":
        return value is None
    if operator == "present":
        return value is not None
    if operator == "is_true":
        return value is True
    if operator == "is_false":
        return value is False
    raise ValueError(f"Unsupported operator: {operator}")


def evaluate_condition_group(resource: dict[str, Any], group: dict[str, Any]) -> bool:
    conditions = group.get("conditions") or []
    if not conditions:
        return False
    results = [evaluate_condition(resource, condition) for condition in conditions]
    group_type = group.get("type") or "all"
    if group_type == "all":
        return all(results)
    if group_type == "any":
        return any(results)
    raise ValueError(f"Unsupported condition group type: {group_type}")


def classify_score(score: float, levels: list[dict[str, Any]]) -> str:
    for level in levels:
        low, high = level["scoreRange"]
        if low <= score <= high:
            return level["level"]
    return "unknown"


def assess_data_quality(assessment: dict[str, Any], resource: dict[str, Any]) -> dict[str, Any]:
    """Score resource data quality using pythonAssessment deterministic cases."""
    python_assessment = assessment.get("pythonAssessment") or {}
    scoring = python_assessment.get("defaultScoring") or {"startScore": 100, "deductions": {}}
    score = float(scoring.get("startScore", 100))
    matched: list[dict[str, Any]] = []

    severity_for_level = {
        "worst": "critical",
        "bad": "high",
        "warning": "medium",
        "good": "low",
        "best": None,
    }

    deterministic = python_assessment.get("deterministicCases") or {}
    for level in ("worst", "bad", "warning"):
        for condition in deterministic.get(level, []):
            if evaluate_condition(resource, condition):
                severity = severity_for_level[level]
                score -= float((scoring.get("deductions") or {}).get(severity, 0) or 0)
                matched.append({"level": level, "condition": condition})

    caps = scoring.get("caps") or {}
    if get_path(resource, "signals.anyCriticalSecurityFinding"):
        score = min(score, float(caps.get("anyCriticalSecurityFinding", score)))
    if get_path(resource, "signals.anyHighSecurityFinding"):
        score = min(score, float(caps.get("anyHighSecurityFinding", score)))
    if get_path(resource, "signals.anyHighReliabilityFinding"):
        score = min(score, float(caps.get("anyHighReliabilityFinding", score)))
    if get_path(resource, "signals.missingRequiredMetrics"):
        score = min(score, float(caps.get("missingRequiredMetrics", score)))
    if get_path(resource, "signals.missingCostData"):
        score = min(score, float(caps.get("missingCostData", score)))
    if get_path(resource, "signals.unknownProductionOwner"):
        score = min(score, float(caps.get("unknownProductionOwner", score)))

    score = max(0.0, min(100.0, score))
    best_conditions = deterministic.get("best", [])
    best_matched = bool(best_conditions) and all(
        evaluate_condition(resource, condition) for condition in best_conditions
    )
    classification = classify_score(
        score,
        python_assessment.get("classificationLevels") or [],
    )
    if best_matched and not matched:
        classification = "best"
        score = max(score, 90.0)

    return {
        "score": score,
        "classification": classification,
        "matchedConditions": matched,
        "bestConditionsMatched": best_matched,
    }


def _iter_rules(
    assessment: dict[str, Any],
    *,
    include_assessment_rules: bool = True,
    include_recommendation_rules: bool = True,
    include_best_optimization_rules: bool = False,
    rule_filter: str | None = None,
) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    if include_assessment_rules:
        rules.extend(assessment.get("assessmentRules") or [])
    if include_recommendation_rules:
        rules.extend(assessment.get("recommendationRules") or [])
    if include_best_optimization_rules:
        rules.extend(assessment.get("bestOptimizationRules") or [])

    if rule_filter == "data_quality":
        filtered: list[dict[str, Any]] = []
        for rule in rules:
            action = (
                rule.get("recommendationAction")
                or rule.get("actionOutcome")
                or (rule.get("output") or {}).get("recommendationAction")
            )
            pillar = (rule.get("pillar") or "").lower()
            if action == "investigate" or pillar in {"data", "governance", "operations"}:
                filtered.append(rule)
        return filtered
    return rules


def rule_applies_to_resource(
    rule: dict[str, Any],
    resource_type: str,
    *,
    primary_resource_type: str | None = None,
) -> bool:
    """True when rule scope matches the resource ARM type (supports consolidated assessments)."""
    applies = rule.get("appliesToResourceTypes")
    if applies:
        target = (resource_type or "").strip()
        return any(target.lower() == str(item).lower() for item in applies)
    primary = (primary_resource_type or "").strip()
    target = (resource_type or "").strip()
    if not primary:
        # Unscoped rules apply only when the resource type is not set (single-type
        # assessment evaluation). Prevents cross-type leakage in consolidated files.
        return not target
    if not target:
        return False
    return target.lower() == primary.lower()


def evaluate_assessment_rules(
    assessment: dict[str, Any],
    resource: dict[str, Any],
    *,
    include_assessment_rules: bool = True,
    include_recommendation_rules: bool = True,
    include_best_optimization_rules: bool = False,
    rule_filter: str | None = None,
    exclude_investigate: bool = False,
    exclude_metric_gaps: bool = False,
) -> list[dict[str, Any]]:
    """Return matched rules from assessment JSON."""
    matched: list[dict[str, Any]] = []
    resource = refresh_record_signals(resource, assessment)
    resource_type = str(resource.get("resource_type") or "")
    primary_type = str(assessment.get("resourceType") or "")
    seen_ids: set[str] = set()
    for rule in _iter_rules(
        assessment,
        include_assessment_rules=include_assessment_rules,
        include_recommendation_rules=include_recommendation_rules,
        include_best_optimization_rules=include_best_optimization_rules,
        rule_filter=rule_filter,
    ):
        rule_id = str(rule.get("id") or "")
        if rule_id and rule_id in seen_ids:
            continue
        from app.assessment.governance_filter import is_region_governance_rule, region_governance_enabled

        if is_region_governance_rule(rule, rule_id=rule_id) and not region_governance_enabled(assessment):
            continue
        if rule.get("enabled") is False:
            continue
        if not is_json_evaluated_rule(rule):
            continue
        if not rule_applies_to_resource(rule, resource_type, primary_resource_type=primary_type):
            continue
        if exclude_metric_gaps and _is_metric_gap_rule(rule):
            continue
        if _should_skip_investigate_rule(rule, exclude_investigate=exclude_investigate):
            continue
        condition = rule.get("condition")
        if not condition:
            continue
        if evaluate_condition_group(resource, condition):
            if rule_id:
                seen_ids.add(rule_id)
            matched.append(rule)
    return matched


def _is_metric_gap_rule(rule: dict[str, Any]) -> bool:
    """Data-quality rules that fire when metrics are missing — not user-facing recommendations."""
    rid = str(rule.get("id") or "")
    if rid.startswith("metric_") and "_missing" in rid:
        return True
    if "_baseline_missing" in rid:
        return True
    category = str(rule.get("category") or "").lower()
    return category == "metric" and "_missing" in rid


def _is_actionable_investigate_rule(rule: dict[str, Any]) -> bool:
    """Investigate rules that should still surface as user-facing recommendations."""
    rid = str(rule.get("id") or "")
    if rid.startswith("best_") or rid.startswith("servicebus_"):
        return True
    if rule.get("category") == "best_optimization":
        return True
    pillar = str(rule.get("pillar") or "").lower()
    if rule.get("backendCompatible") and pillar in {
        "cost",
        "performance",
        "reliability",
        "security",
        "governance",
    }:
        return True
    return False


def _should_skip_investigate_rule(rule: dict[str, Any], *, exclude_investigate: bool) -> bool:
    if not exclude_investigate:
        return False
    action = (
        rule.get("recommendationAction")
        or rule.get("actionOutcome")
        or (rule.get("output") or {}).get("recommendationAction")
    )
    if action != "investigate":
        return False
    return not _is_actionable_investigate_rule(rule)


def refresh_record_signals(
    resource: dict[str, Any],
    assessment: dict[str, Any] | None,
    *,
    required_metric_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Recompute signals using assessment-level region/pillar overrides."""
    from app.assessment.signals import compute_signals

    record = dict(resource)
    record["signals"] = compute_signals(
        record,
        required_metric_keys=required_metric_keys,
        assessment=assessment,
    )
    return record


def assess_resource(assessment: dict[str, Any], resource: dict[str, Any]) -> dict[str, Any]:
    """Full assessment: data quality score + matched recommendation rules."""
    quality = assess_data_quality(assessment, resource)
    matched_rules = evaluate_assessment_rules(
        assessment,
        resource,
        include_assessment_rules=True,
        include_recommendation_rules=True,
    )
    simplified = []
    for rule in matched_rules:
        output = rule.get("output") or {}
        simplified.append({
            "id": rule.get("id"),
            "pillar": rule.get("pillar"),
            "severity": rule.get("severity"),
            "recommendation": rule.get("recommendation") or output.get("message"),
            "confidence": rule.get("confidence"),
            "recommendationAction": (
                rule.get("recommendationAction")
                or rule.get("actionOutcome")
                or output.get("recommendationAction")
            ),
            "condition": rule.get("condition"),
        })

    return {
        "resource_id": resource.get("resource_id"),
        "resource_type": resource.get("resource_type"),
        "assessment_file": assessment.get("_file"),
        "score": quality["score"],
        "classification": quality["classification"],
        "matchedConditions": quality["matchedConditions"],
        "matchedRecommendationRules": simplified,
        "bestConditionsMatched": quality["bestConditionsMatched"],
    }


def _signal_evidence(resource: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    """Attach human-readable signal values referenced by a matched rule."""
    signals = dict(resource.get("signals") or {})
    evidence: dict[str, Any] = {}
    condition = rule.get("condition") or {}
    for item in condition.get("conditions") or []:
        field = str(item.get("field") or item.get("path") or "")
        if not field.startswith("signals."):
            continue
        key = field.split(".", 1)[1]
        value = get_path(resource, field)
        if value is not None:
            evidence[key] = value

    rid = str(rule.get("id") or "")
    if "region" in rid or "unapproved" in rid:
        for key in (
            "currentRegion",
            "recommendedRegion",
            "recommendedRegionDisplay",
            "regionClassification",
            "regionApproved",
            "regionMigrationRequired",
        ):
            if key in signals:
                evidence[key] = signals[key]
    return evidence


def rule_to_finding(
    rule: dict[str, Any],
    *,
    resource: dict[str, Any],
    assessment_file: str | None = None,
    assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map a matched assessment rule to an OptimizationFinding dict."""
    from app.assessment.what_if import enrich_finding_with_what_if

    output = rule.get("output") or {}
    severity = str(rule.get("severity") or "medium").upper()
    if severity not in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}:
        severity = "MEDIUM"

    detail = (
        output.get("message")
        or rule.get("recommendation")
        or output.get("shortMessage")
        or rule.get("id")
        or "Assessment recommendation"
    )
    recommendation = (
        output.get("recommendedActionText")
        or output.get("shortMessage")
        or rule.get("recommendation")
        or detail
    )
    region_text = _personalize_region_recommendation(rule, resource, assessment=assessment)
    if region_text:
        detail, recommendation, rule_name = region_text
    else:
        rule_name = _humanize_assessment_rule_name(rule, detail=detail)

    finding = {
        "rule_id": rule.get("id") or "assessment_rule",
        "rule_name": rule_name,
        "category": (rule.get("pillar") or "cost").lower(),
        "severity": severity,
        "resource_id": resource.get("resource_id") or "",
        "resource_name": resource.get("resource", {}).get("name") or resource.get("resource_name") or "",
        "resource_type": resource.get("resource_type") or "",
        "resource_group": resource.get("resource", {}).get("resource_group") or resource.get("resource_group") or "",
        "location": resource.get("resource", {}).get("location") or resource.get("location") or "",
        "detail": detail,
        "recommendation": recommendation,
        "estimated_savings_usd": float(output.get("estimatedMonthlySavingsUsd") or 0),
        "evidence": {
            "assessment_file": assessment_file,
            "recommendation_action": (
                "migrate_region"
                if "unapproved_region" in str(rule.get("id") or "")
                else (
                    rule.get("recommendationAction")
                    or rule.get("actionOutcome")
                    or output.get("recommendationAction")
                )
            ),
            "pillar": rule.get("pillar"),
            "confidence": rule.get("confidence"),
            "engine": "assessment_json",
            "rule_source": "assessment_json",
        },
        "status": "open",
    }
    if assessment:
        finding = enrich_finding_with_what_if(finding, assessment, rule, resource=resource)
    signal_evidence = _signal_evidence(resource, rule)
    if signal_evidence:
        evidence = dict(finding.get("evidence") or {})
        evidence["signals"] = signal_evidence
        finding = dict(finding)
        finding["evidence"] = evidence
    return finding


def _strip_optimization_prefix(text: str) -> str:
    return _AZURE_OPTIMIZATION_PREFIX.sub("", text).strip()


def _personalize_region_recommendation(
    rule: dict[str, Any],
    resource: dict[str, Any],
    *,
    assessment: dict[str, Any] | None = None,
) -> tuple[str, str, str] | None:
    """Build resource-specific region migration copy for best_unapproved_region."""
    rid = str(rule.get("id") or "")
    if "unapproved_region" not in rid:
        return None

    from app.assessment.region_governance import region_display_name, service_override

    signals = resource.get("signals") or {}
    current = signals.get("currentRegion") or resource.get("location") or ""
    target = signals.get("recommendedRegion") or "canadacentral"
    target_display = signals.get("recommendedRegionDisplay") or region_display_name(
        target, assessment=assessment,
    )
    current_display = region_display_name(current, assessment=assessment) if current else "unknown"
    resource_type = str(resource.get("resource_type") or "")
    override = service_override(resource_type, assessment=assessment)
    migration_note = str(override.get("migration_notes") or "").strip()
    if not migration_note and "disks" in resource_type.lower():
        migration_note = (
            "Managed disks cannot change region in place. Snapshot the disk, copy to the "
            "target region, and attach it to a VM in that region."
        )

    detail_parts = [
        f"Resource is in {current_display} ({current}), which is not an approved region.",
        f"Plan migration to {target_display} ({target}).",
    ]
    if migration_note:
        detail_parts.append(migration_note)
    detail_parts.append("Use Canada East (canadaeast) only for DR pairing.")
    detail = " ".join(detail_parts)
    rule_name = (
        f"Move from {current_display} to {target_display}"
        if current else f"Move to {target_display}"
    )
    return detail, detail, rule_name


def _humanize_assessment_rule_name(rule: dict[str, Any], *, detail: str = "") -> str:
    output = rule.get("output") or {}
    for key in ("shortMessage", "message", "recommendedActionText"):
        text = str(output.get(key) or "").strip()
        if text:
            text = _strip_optimization_prefix(text)
            if len(text) > 140:
                text = text[:137].rstrip() + "…"
            return text
    rid = str(rule.get("id") or "")
    if rid.startswith("metric_") and "_missing" in rid:
        metric = rid.replace("metric_", "").replace("_missing", "").replace("_", " ")
        return f"Sync {metric} metric from Azure Monitor"
    if detail and not detail.startswith("metric_"):
        return detail[:140]
    return rid.replace("_", " ").strip().title() or "Assessment recommendation"
