"""Read metric and data-quality requirements from assessment JSON files."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

_COST_FIELD_KEYS = frozenset({
    "monthlyActualCost",
    "monthly_cost_usd",
    "monthlyCostUsd",
    "mtdCostUsd",
})

_PROPERTY_FIELD_KEYS = frozenset({
    "vmSize",
    "diskSizeGB",
    "sku.name",
    "properties.tier",
    "pricingModel",
    "licenseType",
    "runningHours",
    "billed_mtd",
    "retail_monthly",
})


def _schema_version(assessment: dict[str, Any]) -> str:
    return str(assessment.get("schema_version") or assessment.get("schemaVersion") or "")


def _is_v2_assessment(assessment: dict[str, Any]) -> bool:
    return _schema_version(assessment).startswith("2")


def _metrics_fallback_lists(assessment: dict[str, Any]) -> list[dict[str, Any]]:
    for key, value in assessment.items():
        if key == "supportedMetricsFallback":
            return list(value or [])
        if key.startswith("supported") and key.endswith("MetricsFallback") and isinstance(value, list):
            return list(value)
    return []


def monitor_metric_names(assessment: dict[str, Any]) -> tuple[str, ...]:
    """Azure Monitor metric names to fetch for this assessment file."""
    names: list[str] = []

    if _is_v2_assessment(assessment):
        azure_metrics = assessment.get("azure_metrics") or {}
        for item in azure_metrics.get("metrics") or []:
            name = str(item.get("metric_name") or "").strip()
            if name:
                names.append(name)

    for item in _metrics_fallback_lists(assessment):
        name = (item.get("restApiName") or item.get("displayName") or "").strip()
        if name:
            names.append(name)

    plan = assessment.get("lowCallCollectionPlan") or {}
    for step in plan.get("minimumCallFlowPerSubscription") or []:
        for name in step.get("metricnames") or []:
            text = str(name).strip()
            if text:
                names.append(text)

    recommended = assessment.get("recommendedMetricRequest") or {}
    for template in recommended.values():
        if not isinstance(template, str) or "metricnames=" not in template:
            continue
        query = urlparse(template).query
        parsed = parse_qs(query)
        raw = (parsed.get("metricnames") or [""])[0]
        for part in unquote(raw).split(","):
            text = part.strip()
            if text:
                names.append(text)

    return tuple(dict.fromkeys(names))


def required_metric_keys(assessment: dict[str, Any]) -> list[str]:
    """Normalized metric/signal keys required for scoring and rules."""
    keys: set[str] = set()

    if _is_v2_assessment(assessment):
        azure_metrics = assessment.get("azure_metrics") or {}
        for item in azure_metrics.get("metrics") or []:
            fact_key = str(item.get("fact_key") or "").strip()
            if fact_key:
                keys.add(fact_key)
        for key in (azure_metrics.get("derived_metrics") or {}):
            keys.add(str(key))
        for case in assessment.get("cases") or []:
            for metric_key in case.get("metrics_required") or []:
                text = str(metric_key).strip()
                if text:
                    keys.add(text)
        for rule in assessment.get("rules") or []:
            for item in rule.get("required_evidence") or []:
                signal = str(item.get("signal") or "").strip()
                if signal and signal not in _COST_FIELD_KEYS and signal not in _PROPERTY_FIELD_KEYS:
                    keys.add(signal)

    for item in assessment.get("costOptimizationSignals") or []:
        text = str(item).strip()
        if not text or text in _COST_FIELD_KEYS or text in _PROPERTY_FIELD_KEYS:
            continue
        if "." in text:
            root, leaf = text.split(".", 1)
            if root in {"metrics", "signals"}:
                keys.add(leaf)
            continue
        keys.add(text)

    for key in (assessment.get("derivedMetrics") or {}):
        keys.add(str(key))

    python_assessment = assessment.get("pythonAssessment") or {}
    for cases in (python_assessment.get("deterministicCases") or {}).values():
        for condition in cases or []:
            field = str(condition.get("field") or condition.get("path") or "")
            if field.startswith("signals."):
                keys.add(field.split(".", 1)[1])
            elif field.startswith("metrics."):
                keys.add(field.split(".", 1)[1])

    for rule_list_name in (
        "assessmentRules",
        "recommendationRules",
        "bestOptimizationRules",
        "metricAssessmentRules",
        "propertyAssessmentRules",
    ):
        for rule in assessment.get(rule_list_name) or []:
            for path in rule.get("requiredData") or []:
                text = str(path)
                if text.startswith("signals."):
                    keys.add(text.split(".", 1)[1])
                elif text.startswith("metrics."):
                    keys.add(text.split(".", 1)[1])

    return sorted(k for k in keys if k and not k.startswith("_"))


def required_normalized_input(assessment: dict[str, Any]) -> list[str]:
    python_assessment = assessment.get("pythonAssessment") or {}
    return list(python_assessment.get("requiredNormalizedInput") or [])


def metrics_refresh_timespan(assessment: dict[str, Any]) -> str | None:
    """Optional lookback hint from assessment strategy (falls back to env defaults)."""
    if _is_v2_assessment(assessment):
        period = str((assessment.get("azure_metrics") or {}).get("period_default") or "").strip()
        if period:
            return period

    strategy = assessment.get("strategy") or {}
    cadence = strategy.get("refreshCadence") or {}
    metrics_cadence = str(cadence.get("metrics") or "").strip().lower()
    if "hourly" in metrics_cadence or "daily" in metrics_cadence:
        return None
    recommended = assessment.get("recommendedMetricRequest") or {}
    preferred = str(recommended.get("preferredInterval") or "")
    if "30_day" in preferred or "30 day" in preferred:
        return "P30D"
    if "7_day" in preferred or "7 day" in preferred:
        return "P7D"
    return None


def assessment_metadata(assessment: dict[str, Any]) -> dict[str, Any]:
    """Compact assessment reference stored on normalized snapshots."""
    strategy = assessment.get("strategy") or {}
    return {
        "assessment_file": assessment.get("_file"),
        "assessment_name": assessment.get("assessmentName") or assessment.get("assessment_name"),
        "resource_type": assessment.get("resourceType") or assessment.get("resource_type"),
        "schema_version": _schema_version(assessment) or None,
        "runtime_data_source": strategy.get("runtimeDataSource"),
        "analyzer_uses_stored_metrics_only": strategy.get("analyzerUsesStoredMetricsOnly"),
        "monitor_metric_names": list(monitor_metric_names(assessment)),
        "required_metric_keys": required_metric_keys(assessment),
        "required_normalized_input": required_normalized_input(assessment),
    }


def sanitize_metric_fact_key(name: str) -> str:
    """Fallback fact key when no monitor profile mapping exists."""
    text = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()
    return text or "metric_value"
