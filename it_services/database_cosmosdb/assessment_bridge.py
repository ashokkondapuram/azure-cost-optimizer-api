"""Cosmos DB assessment bridge — cosmosdb-assessment.json is the single source of truth."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.assessment.catalog import get_assessment_for_arm_type
from app.assessment.spec import monitor_metric_names, required_metric_keys
from app.optimizer.advanced_rules import AdvancedRule

COSMOS_ARM_TYPE = "Microsoft.DocumentDB/databaseAccounts"
ASSESSMENT_FILE = "cosmosdb-assessment.json"

_THRESHOLD_FIELD_MAP: dict[str, str] = {
    "cosmos_ru_low_pct": "cosmos_ru_low_pct",
    "cosmos_ru_high_pct": "cosmos_ru_high_pct",
    "cosmos_throttle_ru_pct": "cosmos_throttle_ru_pct",
    "cosmos_serverless_ru_threshold": "cosmos_serverless_ru_threshold",
    "cosmos_autoscale_candidate_utilization_pct": "cosmos_autoscale_candidate_utilization_pct",
    "cosmos_hot_partition_skew_ratio": "cosmos_hot_partition_skew_ratio",
    "cosmos_large_item_bytes": "cosmos_large_item_bytes",
    "cosmos_index_to_data_ratio": "cosmos_index_to_data_ratio",
    "cosmos_replication_lag_ms": "cosmos_replication_lag_ms",
    "min_monthly_savings_usd": "min_monthly_savings_usd",
    "evaluation_window_days": "evaluation_window_days",
}

_SIGNAL_TO_FACT_KEY: dict[str, str] = {
    "ru_utilization_pct": "normalized_ru_pct",
    "ru_utilization_peak_pct": "normalized_ru_peak_pct",
    "total_ru_consumed": "total_ru",
    "request_count": "request_count",
    "provisioned_throughput": "provisioned_throughput",
    "ru_skew_ratio": "ru_skew_ratio",
    "avg_item_bytes": "avg_item_bytes",
    "index_to_data_ratio": "index_to_data_ratio",
    "data_usage_bytes": "data_usage_bytes",
    "index_usage_bytes": "index_usage_bytes",
    "document_count": "document_count",
    "replication_latency_ms": "replication_latency_ms",
    "server_latency_ms": "server_latency_ms",
}

_THRESHOLD_COMPARATOR: dict[str, str] = {
    "cosmos_ru_low_pct": "<",
    "cosmos_ru_high_pct": ">",
    "cosmos_throttle_ru_pct": "≥",
    "cosmos_serverless_ru_threshold": "<",
    "cosmos_hot_partition_skew_ratio": ">",
    "cosmos_large_item_bytes": ">",
    "cosmos_index_to_data_ratio": ">",
}


@lru_cache(maxsize=1)
def load_cosmos_assessment() -> dict[str, Any]:
    assessment = get_assessment_for_arm_type(COSMOS_ARM_TYPE)
    if not assessment:
        raise FileNotFoundError(f"{ASSESSMENT_FILE} not indexed for {COSMOS_ARM_TYPE}")
    return assessment


def clear_cosmos_assessment_cache() -> None:
    load_cosmos_assessment.cache_clear()
    get_assessment_for_arm_type.cache_clear()


def cosmos_rule_ids() -> list[str]:
    return [str(r.get("rule_id") or "") for r in load_cosmos_assessment().get("rules") or [] if r.get("rule_id")]


def cosmos_rule_by_id(rule_id: str) -> dict[str, Any] | None:
    rid = (rule_id or "").upper()
    for rule in load_cosmos_assessment().get("rules") or []:
        if str(rule.get("rule_id") or "").upper() == rid:
            return dict(rule)
    return None


def cosmos_cases() -> list[dict[str, Any]]:
    return list(load_cosmos_assessment().get("cases") or [])


def cosmos_sync_property_paths() -> tuple[str, ...]:
    paths = (load_cosmos_assessment().get("azure_properties") or {}).get("sync_property_paths") or []
    return tuple(str(p) for p in paths if p)


def cosmos_arm_property_paths() -> tuple[str, ...]:
    paths: list[str] = []
    azure_props = load_cosmos_assessment().get("azure_properties") or {}
    for group in azure_props.get("groups") or []:
        for prop in group.get("properties") or []:
            if not isinstance(prop, dict):
                continue
            arm_path = str(prop.get("arm_path") or "").strip()
            if arm_path:
                paths.append(arm_path)
    return tuple(dict.fromkeys(paths))


def cosmos_metrics_period_default() -> str:
    period = str((load_cosmos_assessment().get("azure_metrics") or {}).get("period_default") or "").strip()
    return period or "P7D"


def cosmos_monitor_metrics() -> tuple[Any, ...]:
    from app.resources.types import utilization_metric as um

    assessment = load_cosmos_assessment()
    azure_metrics = assessment.get("azure_metrics") or {}
    period_default = cosmos_metrics_period_default()
    out: list[Any] = []
    for item in azure_metrics.get("metrics") or []:
        if not isinstance(item, dict):
            continue
        metric_name = str(item.get("metric_name") or "").strip()
        fact_key = str(item.get("fact_key") or "").strip()
        if not metric_name or not fact_key:
            continue
        rules = tuple(str(r) for r in (item.get("rules") or []) if r)
        out.append(
            um(
                metric_name,
                fact_key,
                str(item.get("description") or item.get("label") or fact_key),
                aggregation=str(item.get("aggregation") or "Average"),
                timespan=str(item.get("period") or period_default),
                rules=rules,
            )
        )
    return tuple(out)


def build_cosmos_monitor_profile() -> Any:
    from app.resources.types import ResourceMonitorProfile

    assessment = load_cosmos_assessment()
    return ResourceMonitorProfile(
        monitor_arm_type=str(assessment.get("arm_type") or "microsoft.documentdb/databaseaccounts"),
        canonical_type=str(assessment.get("resource_type") or "database/cosmosdb"),
        display_name="Cosmos DB account",
        doc_ref="microsoft-documentdb-databaseaccounts-metrics",
        metrics=cosmos_monitor_metrics(),
    )


def cosmos_cost_fields() -> tuple[dict[str, Any], ...]:
    fields = (load_cosmos_assessment().get("cost_management") or {}).get("fields") or []
    return tuple(dict(item) for item in fields if isinstance(item, dict))


def cosmos_cost_field_names() -> tuple[str, ...]:
    return tuple(str(item.get("field") or "").strip() for item in cosmos_cost_fields() if item.get("field"))


def cosmos_metric_fact_keys() -> tuple[str, ...]:
    assessment = load_cosmos_assessment()
    keys: list[str] = []
    for item in (assessment.get("azure_metrics") or {}).get("metrics") or []:
        fact = str(item.get("fact_key") or "").strip()
        if fact:
            keys.append(fact)
    for key in (assessment.get("azure_metrics") or {}).get("derived_metrics") or {}:
        keys.append(str(key))
    return tuple(dict.fromkeys(keys))


def cosmos_monitor_metric_names() -> tuple[str, ...]:
    return monitor_metric_names(load_cosmos_assessment())


def cosmos_required_metric_keys() -> list[str]:
    return required_metric_keys(load_cosmos_assessment())


def optimization_thresholds() -> dict[str, float]:
    raw = load_cosmos_assessment().get("optimization_thresholds") or {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        if value is None:
            continue
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def cost_field_mapping() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in (load_cosmos_assessment().get("cost_management") or {}).get("fields") or []:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "").strip()
        normalized = str(item.get("normalized_key") or item.get("field") or "").strip()
        if field and normalized:
            mapping[field] = normalized
    return mapping


def billed_mtd_normalized_key() -> str:
    return cost_field_mapping().get("billed_mtd", "monthly_cost_usd")


def retail_monthly_normalized_key() -> str:
    return cost_field_mapping().get("retail_monthly", "retail_monthly")


def rule_evidence_factors(rule_id: str) -> list[str]:
    rule = cosmos_rule_by_id(rule_id) or {}
    factors = rule.get("evidence_factors") or []
    return [str(f) for f in factors if f]


def rule_required_evidence(rule_id: str) -> list[dict[str, Any]]:
    rule = cosmos_rule_by_id(rule_id) or {}
    raw = rule.get("required_evidence") or []
    return [dict(item) for item in raw if isinstance(item, dict)]


def resolve_threshold_ref(ref: str) -> float | int | None:
    text = (ref or "").strip()
    if not text:
        return None
    assessment = load_cosmos_assessment()
    if text.startswith("optimization_thresholds."):
        key = text.split(".", 1)[1]
        val = (assessment.get("optimization_thresholds") or {}).get(key)
        return float(val) if val is not None else None
    val = (assessment.get("optimization_thresholds") or {}).get(text)
    if val is not None:
        return float(val)
    return None


def _format_bytes(value: float | int | None) -> str:
    if value is None:
        return "—"
    size = float(value)
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{int(size):,} bytes"


def _format_threshold_label(threshold_key: str) -> str:
    if not threshold_key:
        return "—"
    resolved = resolve_threshold_ref(threshold_key)
    if resolved is None:
        return "—"
    comparator = _THRESHOLD_COMPARATOR.get(threshold_key, "<")
    if str(threshold_key).endswith("_pct"):
        return f"{comparator} {float(resolved):g}%"
    if str(threshold_key).endswith("_bytes"):
        return f"{comparator} {_format_bytes(resolved)}"
    if str(threshold_key).endswith("_ratio"):
        return f"{comparator} {float(resolved):g}x"
    if str(threshold_key).endswith("_threshold"):
        return f"{comparator} {float(resolved):,.0f}"
    return f"{comparator} {resolved}"


def _fact_value_for_signal(signal: str, facts: dict[str, Any]) -> Any:
    fact_key = _SIGNAL_TO_FACT_KEY.get(signal, signal)
    if fact_key in facts and facts[fact_key] is not None:
        return facts[fact_key]
    if signal in facts and facts[signal] is not None:
        return facts[signal]
    opt = facts.get("optimization_metrics") or {}
    for block in (opt.get("performance") or []):
        if not isinstance(block, dict):
            continue
        block_id = str(block.get("id") or block.get("fact_key") or "")
        if block_id in {signal, fact_key}:
            return block.get("value")
    return None


def _format_signal_value(signal: str, raw: Any, *, unit: str = "") -> str:
    if raw is None or raw == "":
        return "—"
    if str(unit).strip() == "%" or str(signal).endswith("_pct"):
        try:
            return f"{float(raw):g}%"
        except (TypeError, ValueError):
            return str(raw)
    if signal in {"avg_item_bytes", "data_usage_bytes", "index_usage_bytes"}:
        try:
            return _format_bytes(float(raw))
        except (TypeError, ValueError):
            return str(raw)
    if signal == "total_ru_consumed":
        try:
            return f"{float(raw):,.0f} RU"
        except (TypeError, ValueError):
            return str(raw)
    if signal == "ru_skew_ratio":
        try:
            return f"{float(raw):.1f}x"
        except (TypeError, ValueError):
            return str(raw)
    if isinstance(raw, (int, float)):
        if float(raw).is_integer():
            return f"{int(raw):,}"
        return f"{float(raw):g}"
    return str(raw)


def _signal_status(signal: str, raw: Any, *, rule_id: str, threshold_key: str) -> str:
    if raw is None:
        return "muted"
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return "muted"

    rid = (rule_id or "").upper()
    limit = resolve_threshold_ref(threshold_key) if threshold_key else None

    if signal == "ru_utilization_pct":
        if rid in {"COSMOS_RU_RIGHT_SIZING_UNDER", "COSMOS_AUTOSCALE_EXTENDED", "COSMOS_RESERVED_CAPACITY_ELIGIBLE"}:
            if limit is not None and value < float(limit):
                return "pass"
            return "warn"
        if rid == "COSMOS_RU_RIGHT_SIZING_OVER":
            if limit is not None and value >= float(limit):
                return "fail"
            return "warn"

    if signal == "ru_utilization_peak_pct":
        if limit is not None and value >= float(limit):
            return "fail"
        return "warn"

    if signal == "total_ru_consumed":
        if limit is not None and value < float(limit):
            return "pass"
        return "warn"

    if signal == "ru_skew_ratio":
        if limit is not None and value >= float(limit):
            return "fail"
        return "pass"

    if signal == "index_to_data_ratio":
        if limit is not None and value >= float(limit):
            return "fail"
        return "pass"

    if signal == "avg_item_bytes":
        if limit is not None and value >= float(limit):
            return "fail"
        return "pass"

    return "muted"


def build_structured_evidence_rows(rule_id: str, facts: dict[str, Any]) -> list[dict[str, Any]]:
    required = rule_required_evidence(rule_id)
    if not required:
        return []

    rows: list[dict[str, Any]] = []
    for item in required:
        signal = str(item.get("signal") or "").strip()
        if not signal:
            continue
        threshold_key = str(item.get("threshold_key") or "").strip()
        raw = _fact_value_for_signal(signal, facts)
        rows.append({
            "signal": signal,
            "label": str(item.get("label") or signal.replace("_", " ").title()),
            "value": _format_signal_value(signal, raw, unit=str(item.get("unit") or "")),
            "threshold": _format_threshold_label(threshold_key),
            "aggregation": str(item.get("aggregation") or ""),
            "period": str(item.get("period") or ""),
            "unit": str(item.get("unit") or ""),
            "pillar": str(item.get("pillar") or "performance"),
            "status": _signal_status(signal, raw, rule_id=rule_id, threshold_key=threshold_key),
        })
    return rows


def augment_finding_evidence(rule_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
    out = dict(evidence)
    factors = rule_evidence_factors(rule_id)
    if factors:
        out["evidence_factors"] = factors
    required = rule_required_evidence(rule_id)
    if required:
        out["required_evidence"] = required
    rows = build_structured_evidence_rows(rule_id, out)
    if rows:
        out["evidence_rows"] = rows
    out["exclude_inventory_facts"] = True
    out["_evidence_meta"] = {"assessment_file": ASSESSMENT_FILE}
    out.pop("assessment_file", None)
    return out


def _apply_thresholds_to_rule(rule: AdvancedRule, rule_id: str) -> None:
    thresholds = optimization_thresholds()
    for src_key, field_name in _THRESHOLD_FIELD_MAP.items():
        if src_key in thresholds and hasattr(rule, field_name):
            value = thresholds[src_key]
            if field_name == "evaluation_window_days":
                setattr(rule, field_name, int(value))
            else:
                setattr(rule, field_name, float(value))


def hydrate_cosmos_rules(rules: dict[str, AdvancedRule]) -> None:
    """Apply cosmosdb-assessment.json thresholds to engine AdvancedRule instances."""
    for rule_id in cosmos_rule_ids():
        rule = rules.get(rule_id)
        if rule is None:
            continue
        _apply_thresholds_to_rule(rule, rule_id)


def extended_cosmos_spec_payload() -> dict[str, Any]:
    from app.optimizer.advanced_rules import ADVANCED_RULES
    from app.optimizer.rule_catalog import RULE_MANIFEST

    assessment = load_cosmos_assessment()
    applied: list[dict[str, Any]] = []
    for rule_id in cosmos_rule_ids():
        cfg = cosmos_rule_by_id(rule_id) or {}
        catalog = RULE_MANIFEST.get(rule_id) or {}
        advanced = ADVANCED_RULES.get(rule_id)
        applied.append({
            "rule_id": rule_id,
            "engine": cfg.get("engine") or catalog.get("engine", "extended"),
            "component": catalog.get("component", "Cosmos DB"),
            "enabled": bool(getattr(advanced, "enabled", True)) if advanced else True,
            "savings_basis": (cfg.get("recommendation") or {}).get("savings_from") or "azure_billed_mtd",
            "category": cfg.get("category"),
            "determines": cfg.get("determines"),
            "required_evidence": cfg.get("required_evidence"),
            "evidence_factors": cfg.get("evidence_factors"),
            "recommendation": cfg.get("recommendation"),
        })
    cost_policy = assessment.get("cost_policy") or {}
    return {
        "canonical_type": assessment.get("resource_type", "database/cosmosdb"),
        "schema_version": assessment.get("schema_version") or assessment.get("schemaVersion"),
        "assessment_file": ASSESSMENT_FILE,
        "assessment_name": assessment.get("assessmentName"),
        "optimization_thresholds": optimization_thresholds(),
        "azure_metrics": assessment.get("azure_metrics"),
        "cost_management": assessment.get("cost_management"),
        "cases": cosmos_cases(),
        "analysis_rules": applied,
        "cost_source": cost_policy.get("source", "azure_cost_management"),
    }
