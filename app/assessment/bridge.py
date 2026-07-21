"""Bridge inventory envelopes to assessment JSON rule evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from app.assessment.advisor_bridge import build_policy_from_advisor
from app.assessment.catalog import get_assessment_for_arm_type
from app.assessment.normalizer import build_normalized_record
from app.cost_utils import resource_cost
from app.focus_mapping import normalize_arm_id
from app.optimizer.platform.runtime.context import AnalysisContext
from app.resource_type_map import arm_provider_type
from app.resources.registry import TECHNICAL_FETCH_SPECS

_CONFIDENCE_LABEL_SCORES = {
    "very_high": 90,
    "high": 85,
    "medium": 70,
    "low": 50,
    "very_low": 40,
}
_DEFAULT_CONFIDENCE_SCORE = 70

_ARM_TYPE_BY_CANONICAL: dict[str, str] = {
    ct: spec.arm_type
    for ct, spec in TECHNICAL_FETCH_SPECS.items()
    if getattr(spec, "arm_type", None)
}
_CANONICAL_BY_ARM: dict[str, str] = {
    arm.lower(): ct for ct, arm in _ARM_TYPE_BY_CANONICAL.items()
}


def normalize_confidence_score(value: Any, *, default: int = _DEFAULT_CONFIDENCE_SCORE) -> int:
    """Map assessment rule confidence (label or 0–100 score) to an integer score."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return max(0, min(100, int(round(value))))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        if stripped.isdigit():
            return max(0, min(100, int(stripped)))
        mapped = _CONFIDENCE_LABEL_SCORES.get(stripped.lower())
        if mapped is not None:
            return mapped
        try:
            return max(0, min(100, int(round(float(stripped)))))
        except ValueError:
            return default
    return default


def _extract_rg(resource_id: str) -> str:
    parts = (resource_id or "").split("/")
    for idx, part in enumerate(parts):
        if part.lower() == "resourcegroups" and idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


def resource_to_assessment_record(
    resource: dict[str, Any],
    ctx: AnalysisContext,
) -> dict[str, Any]:
    """Convert a prepared sub-engine resource into the assessment runtime record shape."""
    rid = normalize_arm_id(resource.get("id") or "")
    arm_type = (arm_provider_type(rid) or resource.get("type") or "").strip()
    facts = dict(resource.get("_technical_facts") or {})
    elements = dict(resource.get("_resource_elements") or {})
    runtime = dict(elements.get("runtime") or {})
    cost_block = dict(elements.get("cost") or {})
    monthly = float(
        cost_block.get("monthly_usd")
        or resource_cost(ctx.cost_by_resource, rid)
        or 0
    )

    metrics = dict(ctx.facts_for_resource(rid.lower()) or {})
    for key, value in runtime.items():
        if key == "metrics_available" or value is None:
            continue
        metrics.setdefault(key, value)
    for key, value in facts.items():
        if isinstance(value, (int, float)):
            metrics.setdefault(key, value)

    advisor_rows = ctx.advisor_for_resource(rid)
    policy = build_policy_from_advisor(advisor_rows) if advisor_rows else {}

    row_dict = {
        "subscription_id": ctx.subscription_id,
        "resource_id": rid,
        "resource_name": resource.get("name") or "",
        "resource_type": arm_type,
        "canonical_type": resource.get("_canonical_type") or "",
        "resource_group": _extract_rg(rid),
        "location": resource.get("location") or "",
        "sku": facts.get("sku") or resource.get("sku") or "",
        "state": resource.get("state") or facts.get("state") or "",
        "properties": dict(resource.get("properties") or {}),
        "tags": dict(resource.get("tags") or {}),
        "monthly_cost_usd": monthly,
        "monthly_cost_billing": monthly,
        "billing_currency": "USD",
    }
    return build_normalized_record(
        row_dict,
        metrics=metrics,
        policy=policy,
        assessment=get_assessment_for_arm_type(arm_type),
    )


def assessment_dict_to_extended_finding(
    finding: dict[str, Any],
    *,
    subscription_id: str,
    resource: dict[str, Any],
):
    """Map assessment rule output to ExtendedFinding for sub-engine pipelines."""
    from app.optimizer.core.finding import ExtendedFinding

    savings = float(finding.get("estimated_savings_usd") or 0)
    evidence = dict(finding.get("evidence") or {})
    evidence.setdefault("engine", "assessment_json")
    evidence.setdefault("rule_source", "assessment_json")

    return ExtendedFinding(
        rule_id=str(finding.get("rule_id") or "assessment_rule"),
        rule_name=str(finding.get("rule_name") or finding.get("rule_id") or "assessment_rule"),
        category=str(finding.get("category") or "cost"),
        severity=str(finding.get("severity") or "MEDIUM").upper(),
        resource_id=str(finding.get("resource_id") or resource.get("id") or ""),
        resource_name=str(finding.get("resource_name") or resource.get("name") or ""),
        resource_type=str(finding.get("resource_type") or resource.get("type") or ""),
        subscription_id=subscription_id,
        resource_group=str(finding.get("resource_group") or _extract_rg(resource.get("id") or "")),
        location=str(finding.get("location") or resource.get("location") or ""),
        detail=str(finding.get("detail") or ""),
        recommendation=str(finding.get("recommendation") or finding.get("detail") or ""),
        estimated_savings_usd=round(savings, 2),
        annualized_savings_usd=round(savings * 12, 2),
        waste_score=50,
        confidence_score=normalize_confidence_score(evidence.get("confidence")),
        action_priority="P2",
        impact=str(finding.get("recommendation") or finding.get("detail") or ""),
        evidence=evidence,
        tags=dict(resource.get("tags") or {}),
        detected_at=datetime.now(timezone.utc).isoformat(),
    )


# --- Assessment config helpers (single JSON per resource type) ---


def canonical_for_arm_type(arm_type: str) -> str:
    return _CANONICAL_BY_ARM.get((arm_type or "").strip().lower(), "")


def arm_type_for_canonical(canonical_type: str) -> str:
    return _ARM_TYPE_BY_CANONICAL.get((canonical_type or "").strip().lower(), "")


@lru_cache(maxsize=64)
def load_assessment_for_canonical(canonical_type: str) -> dict[str, Any] | None:
    arm_type = arm_type_for_canonical(canonical_type)
    if not arm_type:
        return None
    return get_assessment_for_arm_type(arm_type)


@lru_cache(maxsize=64)
def load_assessment_by_arm(arm_type: str) -> dict[str, Any] | None:
    return get_assessment_for_arm_type(arm_type)


def is_v2_assessment(assessment: dict[str, Any]) -> bool:
    schema = str(assessment.get("schema_version") or assessment.get("schemaVersion") or "")
    return schema.startswith("2")


def assessment_file_name(assessment: dict[str, Any]) -> str:
    return str(assessment.get("_file") or "")


def sync_property_paths(assessment: dict[str, Any]) -> tuple[str, ...]:
    if is_v2_assessment(assessment):
        paths = (assessment.get("azure_properties") or {}).get("sync_property_paths") or []
        return tuple(str(p) for p in paths if p)
    legacy = assessment.get("resourceProperties") or assessment.get("syncedPropertyPaths") or []
    out: list[str] = []
    for item in legacy:
        text = str(item).strip()
        if not text:
            continue
        if text.startswith("properties."):
            out.append(text.split(".", 1)[1])
        elif text not in {"id", "name", "type", "location", "tags"}:
            out.append(text)
    return tuple(dict.fromkeys(out))


def arm_property_paths(assessment: dict[str, Any]) -> tuple[str, ...]:
    if is_v2_assessment(assessment):
        paths: list[str] = []
        azure_props = assessment.get("azure_properties") or {}
        for group in azure_props.get("groups") or []:
            for prop in group.get("properties") or []:
                if not isinstance(prop, dict):
                    continue
                arm_path = str(prop.get("arm_path") or "").strip()
                if arm_path:
                    paths.append(arm_path)
        return tuple(dict.fromkeys(paths))
    return sync_property_paths(assessment)


def rule_ids(assessment: dict[str, Any]) -> list[str]:
    if is_v2_assessment(assessment):
        return [
            str(r.get("rule_id") or "")
            for r in assessment.get("rules") or []
            if r.get("rule_id")
        ]
    ids: list[str] = []
    for section in ("recommendationRules", "assessmentRules", "bestOptimizationRules"):
        for rule in assessment.get(section) or []:
            rid = str(rule.get("id") or rule.get("rule_id") or "").strip()
            if rid:
                ids.append(rid)
    return list(dict.fromkeys(ids))


def rule_by_id(assessment: dict[str, Any], rule_id: str) -> dict[str, Any] | None:
    rid = (rule_id or "").upper()
    if is_v2_assessment(assessment):
        for rule in assessment.get("rules") or []:
            if str(rule.get("rule_id") or "").upper() == rid:
                return dict(rule)
        return None
    for section in ("recommendationRules", "assessmentRules", "bestOptimizationRules"):
        for rule in assessment.get(section) or []:
            if str(rule.get("id") or rule.get("rule_id") or "").upper() == rid:
                return dict(rule)
    return None


def optimization_thresholds(assessment: dict[str, Any]) -> dict[str, float]:
    raw = assessment.get("optimization_thresholds") or {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        if value is None:
            continue
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def spec_section(assessment: dict[str, Any], key: str, default: Any = None) -> Any:
    value = assessment.get(key)
    if value is not None:
        return value
    return default


def metrics_period_default(assessment: dict[str, Any]) -> str:
    if is_v2_assessment(assessment):
        period = str((assessment.get("azure_metrics") or {}).get("period_default") or "").strip()
        if period:
            return period
    return "P7D"


def cost_field_mapping(assessment: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    cost_mgmt = assessment.get("cost_management") or {}
    for item in cost_mgmt.get("fields") or []:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "").strip()
        normalized = str(item.get("normalized_key") or item.get("field") or "").strip()
        if field and normalized:
            mapping[field] = normalized
    cost_policy = assessment.get("cost_policy") or {}
    primary = str(cost_policy.get("primary_field") or "").strip()
    normalized_billed = str(cost_policy.get("normalized_billed_key") or "").strip()
    if primary and normalized_billed:
        mapping[primary] = normalized_billed
    retail = str(cost_policy.get("retail_field") or "").strip()
    if retail:
        mapping[retail] = "retail_monthly"
    return mapping


def build_monitor_profile(canonical_type: str) -> Any | None:
    from app.resources.types import ResourceMonitorProfile, utilization_metric as um

    assessment = load_assessment_for_canonical(canonical_type)
    if not assessment or not is_v2_assessment(assessment):
        return None

    azure_metrics = assessment.get("azure_metrics") or {}
    metrics_block = azure_metrics.get("metrics") or []
    if not metrics_block:
        return None

    period_default = metrics_period_default(assessment)
    metrics = []
    for item in metrics_block:
        if not isinstance(item, dict):
            continue
        metric_name = str(item.get("metric_name") or "").strip()
        fact_key = str(item.get("fact_key") or "").strip()
        if not metric_name or not fact_key:
            continue
        rules = tuple(str(r) for r in (item.get("rules") or []) if r)
        metrics.append(
            um(
                metric_name,
                fact_key,
                str(item.get("description") or item.get("label") or fact_key),
                aggregation=str(item.get("aggregation") or "Average"),
                timespan=str(item.get("period") or period_default),
                rules=rules,
            )
        )
    if not metrics:
        return None

    arm_type = arm_type_for_canonical(canonical_type)
    return ResourceMonitorProfile(
        monitor_arm_type=str(assessment.get("arm_type") or arm_type).lower(),
        canonical_type=str(assessment.get("resource_type") or canonical_type),
        display_name=str(assessment.get("assessmentName") or canonical_type),
        doc_ref=str(assessment.get("arm_type") or arm_type).replace("/", "-") + "-metrics",
        metrics=tuple(metrics),
    )


def clear_bridge_cache() -> None:
    load_assessment_for_canonical.cache_clear()
    load_assessment_by_arm.cache_clear()
    get_assessment_for_arm_type.cache_clear()
