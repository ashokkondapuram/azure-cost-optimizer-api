"""Disk assessment bridge — disk-assessment.json is the single source of truth."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.assessment.catalog import get_assessment_for_arm_type
from app.assessment.spec import monitor_metric_names, required_metric_keys
from app.optimizer.advanced_rules import AdvancedRule

DISK_ARM_TYPE = "Microsoft.Compute/disks"
ASSESSMENT_FILE = "disk-assessment.json"

# optimization_thresholds key → AdvancedRule dataclass field
_THRESHOLD_FIELD_MAP: dict[str, str] = {
    "max_unattached_disk_days": "max_unattached_disk_days",
    "disk_io_idle_bps": "disk_io_idle_bps",
    "disk_idle_min_size_gb": "disk_idle_min_size_gb",
    "disk_iops_block_downgrade_pct": "disk_iops_block_downgrade_pct",
    "disk_iops_high_util_pct": "disk_iops_high_util_pct",
    "capacity_used_pct_max": "disk_capacity_used_pct_max",
    "disk_queue_depth_contention": "disk_queue_depth_contention",
    "min_monthly_savings_usd": "min_monthly_savings_usd",
    "evaluation_window_days": "evaluation_window_days",
}

# rule_configurations key → AdvancedRule field (per-rule overrides)
_RULE_CONFIG_FIELD_MAP: dict[str, str] = {
    "grace_period_days": "new_disk_grace_period_days",
    "iops_utilization_threshold_pct": "disk_iops_high_util_pct",
    "throughput_utilization_threshold_pct": "disk_throughput_high_util_pct",
    "min_monthly_savings_usd": "min_monthly_savings_usd",
}


@lru_cache(maxsize=1)
def load_disk_assessment() -> dict[str, Any]:
    assessment = get_assessment_for_arm_type(DISK_ARM_TYPE)
    if not assessment:
        raise FileNotFoundError(f"{ASSESSMENT_FILE} not indexed for {DISK_ARM_TYPE}")
    return assessment


def clear_disk_assessment_cache() -> None:
    load_disk_assessment.cache_clear()
    get_assessment_for_arm_type.cache_clear()


def disk_rule_ids() -> list[str]:
    return [str(r.get("rule_id") or "") for r in load_disk_assessment().get("rules") or [] if r.get("rule_id")]


def disk_rule_by_id(rule_id: str) -> dict[str, Any] | None:
    rid = (rule_id or "").upper()
    for rule in load_disk_assessment().get("rules") or []:
        if str(rule.get("rule_id") or "").upper() == rid:
            return dict(rule)
    return None


def disk_cases() -> list[dict[str, Any]]:
    return list(load_disk_assessment().get("cases") or [])


def disk_sync_property_paths() -> tuple[str, ...]:
    paths = (load_disk_assessment().get("azure_properties") or {}).get("sync_property_paths") or []
    return tuple(str(p) for p in paths if p)


def disk_arm_property_paths() -> tuple[str, ...]:
    """Full ARM paths from azure_properties.groups — inventory enrichment reference."""
    paths: list[str] = []
    azure_props = load_disk_assessment().get("azure_properties") or {}
    for group in azure_props.get("groups") or []:
        for prop in group.get("properties") or []:
            if not isinstance(prop, dict):
                continue
            arm_path = str(prop.get("arm_path") or "").strip()
            if arm_path:
                paths.append(arm_path)
    return tuple(dict.fromkeys(paths))


def disk_metrics_period_default() -> str:
    period = str((load_disk_assessment().get("azure_metrics") or {}).get("period_default") or "").strip()
    return period or "P7D"


def disk_monitor_metrics() -> tuple[Any, ...]:
    """Azure Monitor metric definitions from disk-assessment.json azure_metrics.metrics."""
    from app.resources.types import UtilizationMetric, utilization_metric as um

    assessment = load_disk_assessment()
    azure_metrics = assessment.get("azure_metrics") or {}
    period_default = disk_metrics_period_default()
    out: list[UtilizationMetric] = []
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


def build_disk_monitor_profile() -> Any:
    """ResourceMonitorProfile for managed disks — sourced from disk-assessment.json."""
    from app.resources.types import ResourceMonitorProfile

    assessment = load_disk_assessment()
    return ResourceMonitorProfile(
        monitor_arm_type=str(assessment.get("arm_type") or "microsoft.compute/disks"),
        canonical_type=str(assessment.get("resource_type") or "compute/disk"),
        display_name="Managed disk",
        doc_ref="microsoft-compute-disks-metrics",
        metrics=disk_monitor_metrics(),
    )


def disk_cost_fields() -> tuple[dict[str, Any], ...]:
    """Cost Management / retail field definitions from disk-assessment.json."""
    fields = (load_disk_assessment().get("cost_management") or {}).get("fields") or []
    return tuple(dict(item) for item in fields if isinstance(item, dict))


def disk_cost_field_names() -> tuple[str, ...]:
    return tuple(str(item.get("field") or "").strip() for item in disk_cost_fields() if item.get("field"))


def disk_metric_fact_keys() -> tuple[str, ...]:
    assessment = load_disk_assessment()
    keys: list[str] = []
    for item in (assessment.get("azure_metrics") or {}).get("metrics") or []:
        fact = str(item.get("fact_key") or "").strip()
        if fact:
            keys.append(fact)
    for key in (assessment.get("azure_metrics") or {}).get("derived_metrics") or {}:
        keys.append(str(key))
    return tuple(dict.fromkeys(keys))


def disk_monitor_metric_names() -> tuple[str, ...]:
    return monitor_metric_names(load_disk_assessment())


def disk_required_metric_keys() -> list[str]:
    return required_metric_keys(load_disk_assessment())


def optimization_thresholds() -> dict[str, float]:
    raw = load_disk_assessment().get("optimization_thresholds") or {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        if value is None:
            continue
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def rule_engine_config(rule_id: str) -> dict[str, Any]:
    configs = load_disk_assessment().get("rule_configurations") or {}
    cfg = configs.get((rule_id or "").upper()) or configs.get(rule_id or "")
    return dict(cfg) if isinstance(cfg, dict) else {}


def resolve_threshold_ref(ref: str) -> float | int | None:
    """Resolve thresholds_ref paths like optimization_thresholds.disk_io_idle_bps."""
    text = (ref or "").strip()
    if not text:
        return None
    assessment = load_disk_assessment()
    if text.startswith("optimization_thresholds."):
        key = text.split(".", 1)[1]
        val = (assessment.get("optimization_thresholds") or {}).get(key)
        return float(val) if val is not None else None
    if text.startswith("rule_configurations."):
        parts = text.split(".")
        if len(parts) >= 3:
            cfg = rule_engine_config(parts[1])
            val = cfg.get(parts[2])
            return float(val) if val is not None else None
    val = (assessment.get("optimization_thresholds") or {}).get(text)
    if val is not None:
        return float(val)
    return None


def cost_field_mapping() -> dict[str, str]:
    """Assessment cost field → normalized record key."""
    mapping: dict[str, str] = {}
    for item in (load_disk_assessment().get("cost_management") or {}).get("fields") or []:
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


def rule_recommendation_text(rule_id: str) -> str:
    rule = disk_rule_by_id(rule_id) or {}
    rec = rule.get("recommendation") or {}
    action = str(rec.get("action") or "").strip()
    target = rec.get("target_tier")
    if action and target:
        return f"{action} (target: {target})"
    return action


def rule_target_tier(rule_id: str) -> str | None:
    rule = disk_rule_by_id(rule_id) or {}
    target = (rule.get("recommendation") or {}).get("target_tier")
    return str(target) if target else None


def rule_evidence_factors(rule_id: str) -> list[str]:
    rule = disk_rule_by_id(rule_id) or {}
    factors = rule.get("evidence_factors") or []
    return [str(f) for f in factors if f]


def rule_required_evidence(rule_id: str) -> list[dict[str, Any]]:
    rule = disk_rule_by_id(rule_id) or {}
    raw = rule.get("required_evidence") or []
    return [dict(item) for item in raw if isinstance(item, dict)]


_SIGNAL_TO_FACT_KEY: dict[str, str] = {
    "disk_read_throughput": "disk_read_bps",
    "disk_write_throughput": "disk_write_bps",
    "disk_read_iops": "disk_read_iops",
    "disk_write_iops": "disk_write_iops",
    "disk_iops_utilization_pct": "disk_iops_utilization_pct",
    "disk_throughput_utilization_pct": "disk_throughput_utilization_pct",
    "disk_used_pct": "disk_used_pct",
    "disk_queue_depth": "disk_queue_depth",
    "unattached_days": "unattached_days",
}

# Rule-threshold keys persisted for engine overrides — not UI evidence rows.
_RULE_THRESHOLD_KEYS: frozenset[str] = frozenset({
    "max_unattached_disk_days",
    "disk_io_idle_bps",
    "disk_idle_min_size_gb",
    "disk_iops_block_downgrade_pct",
    "disk_iops_high_util_pct",
    "disk_throughput_high_util_pct",
    "evaluation_window_days",
    "min_monthly_savings_usd",
    "disk_capacity_used_pct_max",
    "disk_queue_depth_contention",
})

_THRESHOLD_COMPARATOR: dict[str, str] = {
    "disk_io_idle_bps": "<",
    "max_unattached_disk_days": ">",
    "disk_iops_high_util_pct": "≥",
    "disk_iops_block_downgrade_pct": "<",
    "disk_capacity_used_pct_max": "<",
    "disk_capacity_low_pct": "<",
    "capacity_used_pct_max": "<",
    "disk_queue_depth_contention": ">",
}


def _format_bps(bps: float | int | None) -> str:
    if bps is None:
        return "—"
    value = float(bps)
    if value < 1024:
        return f"{int(round(value))} B/s"
    if value < 1_048_576:
        return f"{value / 1024:.1f} KB/s"
    return f"{value / 1_048_576:.1f} MB/s"


def _format_threshold_label(threshold_key: str) -> str:
    if not threshold_key:
        return "—"
    resolved = resolve_threshold_ref(f"optimization_thresholds.{threshold_key}")
    if resolved is None:
        resolved = resolve_threshold_ref(threshold_key)
    if resolved is None:
        return "—"
    comparator = _THRESHOLD_COMPARATOR.get(threshold_key, "<")
    if str(threshold_key).endswith("_pct"):
        return f"{comparator} {float(resolved):g}%"
    if str(threshold_key).endswith("_bps"):
        return f"{comparator} {_format_bps(resolved)}"
    if str(threshold_key).endswith("_days"):
        return f"{comparator} {int(resolved)} days"
    if str(threshold_key).endswith("_gb"):
        return f"{comparator} {int(resolved)} GB"
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
    if signal in {"disk_read_throughput", "disk_write_throughput"}:
        try:
            return _format_bps(float(raw))
        except (TypeError, ValueError):
            return str(raw)
    if str(unit).strip() == "%" or str(signal).endswith("_pct"):
        try:
            return f"{float(raw):g}%"
        except (TypeError, ValueError):
            return str(raw)
    if signal == "unattached_days":
        try:
            days = int(float(raw))
            return f"{days} day{'s' if days != 1 else ''}"
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
    rid = (rule_id or "").upper()
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return "muted"

    if signal == "unattached_days":
        limit = resolve_threshold_ref("optimization_thresholds.max_unattached_disk_days")
        if limit is not None and value >= float(limit):
            return "fail"
        return "pass"

    if signal in {"disk_read_throughput", "disk_write_throughput"}:
        limit = resolve_threshold_ref(f"optimization_thresholds.{threshold_key or 'disk_io_idle_bps'}")
        if limit is not None and value <= float(limit):
            return "pass"
        return "warn"

    if signal == "disk_iops_utilization_pct":
        if rid == "DISK_UNDERPROVISIONED":
            limit = resolve_threshold_ref("optimization_thresholds.disk_iops_high_util_pct")
            if limit is not None and value >= float(limit):
                return "fail"
            return "warn"
        block = resolve_threshold_ref("optimization_thresholds.premium_downgrade_peak_iops_pct")
        if block is not None and value >= float(block):
            return "fail"
        if value < 30:
            return "pass"
        if value < 50:
            return "warn"
        return "fail"

    if signal == "disk_throughput_utilization_pct":
        limit = resolve_threshold_ref("optimization_thresholds.disk_iops_high_util_pct")
        if limit is not None and value >= float(limit):
            return "fail"
        return "pass"

    if signal == "disk_queue_depth":
        limit = resolve_threshold_ref("optimization_thresholds.disk_queue_depth_contention") or 10
        return "fail" if value > float(limit) else "pass"

    if signal == "disk_used_pct":
        limit = resolve_threshold_ref("optimization_thresholds.capacity_used_pct_max") or 30
        return "pass" if value <= float(limit) else "warn"

    return "muted"


def build_structured_evidence_rows(rule_id: str, facts: dict[str, Any]) -> list[dict[str, Any]]:
    """Map assessment required_evidence contracts to display rows with live values."""
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


def _nest_rule_thresholds(evidence: dict[str, Any]) -> dict[str, Any]:
    """Move engine threshold overrides out of top-level evidence display keys."""
    out = dict(evidence)
    nested = dict(out.pop("rule_thresholds", None) or {})
    for key in list(out.keys()):
        if key in _RULE_THRESHOLD_KEYS:
            nested[key] = out.pop(key)
    if nested:
        out["rule_thresholds"] = nested
    return out


def metric_keys_for_rule(rule_id: str) -> tuple[str, ...]:
    """Fact keys required for a rule from assessment cases."""
    keys: list[str] = []
    for case in disk_cases():
        if str(case.get("rule_id") or "").upper() == (rule_id or "").upper():
            for key in case.get("metrics_required") or []:
                text = str(key).strip()
                if text:
                    keys.append(_SIGNAL_TO_FACT_KEY.get(text, text))
    return tuple(dict.fromkeys(keys))


def rule_utilization_thresholds(rule_id: str) -> dict[str, float]:
    """Per-rule IOPS/throughput/savings thresholds from assessment."""
    cfg = rule_engine_config(rule_id)
    defaults = optimization_thresholds()
    iops = cfg.get("iops_utilization_threshold_pct")
    throughput = cfg.get("throughput_utilization_threshold_pct")
    min_savings = cfg.get("min_monthly_savings_usd")
    return {
        "iops_pct": float(iops if iops is not None else defaults.get("disk_iops_high_util_pct", 80.0)),
        "throughput_pct": float(
            throughput if throughput is not None else (iops if iops is not None else 50.0)
        ),
        "min_savings": float(min_savings if min_savings is not None else defaults.get("min_monthly_savings_usd", 3.0)),
    }


def grace_period_days() -> int:
    return int(optimization_thresholds().get("new_disk_grace_period_days", 7))


def peak_downgrade_block_iops_pct() -> float:
    return float(optimization_thresholds().get("premium_downgrade_peak_iops_pct", 50.0))


def augment_finding_evidence(rule_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
    """Attach assessment contract metadata and structured evidence rows for UI."""
    out = _nest_rule_thresholds(dict(evidence))
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
            if field_name in {"max_unattached_disk_days", "disk_idle_min_size_gb", "evaluation_window_days"}:
                setattr(rule, field_name, int(value))
            else:
                setattr(rule, field_name, float(value))

    cfg = rule_engine_config(rule_id)
    for src_key, field_name in _RULE_CONFIG_FIELD_MAP.items():
        if src_key not in cfg or not hasattr(rule, field_name):
            continue
        value = cfg[src_key]
        if field_name in {"max_unattached_disk_days", "disk_idle_min_size_gb", "evaluation_window_days"}:
            setattr(rule, field_name, int(value))
        else:
            setattr(rule, field_name, float(value))


def hydrate_disk_rules(rules: dict[str, AdvancedRule]) -> None:
    """Apply disk-assessment.json thresholds to engine AdvancedRule instances."""
    for rule_id in disk_rule_ids():
        rule = rules.get(rule_id)
        if rule is None:
            continue
        _apply_thresholds_to_rule(rule, rule_id)


def extended_disk_spec_payload() -> dict[str, Any]:
    """API payload for disk extended rules — sourced from disk-assessment.json."""
    from app.optimizer.advanced_rules import ADVANCED_RULES
    from app.optimizer.rule_catalog import RULE_MANIFEST

    assessment = load_disk_assessment()
    applied: list[dict[str, Any]] = []
    for rule_id in disk_rule_ids():
        cfg = disk_rule_by_id(rule_id) or {}
        catalog = RULE_MANIFEST.get(rule_id) or {}
        advanced = ADVANCED_RULES.get(rule_id)
        applied.append({
            "rule_id": rule_id,
            "engine": cfg.get("engine") or catalog.get("engine", "extended"),
            "component": catalog.get("component", "Managed Disks"),
            "enabled": bool(getattr(advanced, "enabled", True)) if advanced else True,
            "savings_basis": (cfg.get("recommendation") or {}).get("savings_from") or "azure_billed_mtd",
            "category": cfg.get("category"),
            "determines": cfg.get("determines"),
            "thresholds_ref": cfg.get("thresholds_ref"),
            "required_evidence": cfg.get("required_evidence"),
            "evidence_factors": cfg.get("evidence_factors"),
            "recommendation": cfg.get("recommendation"),
        })
    cost_policy = assessment.get("cost_policy") or {}
    return {
        "canonical_type": assessment.get("resource_type", "compute/disk"),
        "schema_version": assessment.get("schema_version") or assessment.get("schemaVersion"),
        "assessment_file": ASSESSMENT_FILE,
        "assessment_name": assessment.get("assessmentName"),
        "optimization_thresholds": optimization_thresholds(),
        "rule_configurations": assessment.get("rule_configurations") or {},
        "azure_metrics": assessment.get("azure_metrics"),
        "cost_management": assessment.get("cost_management"),
        "cases": disk_cases(),
        "analysis_rules": applied,
        "cost_source": cost_policy.get("source", "azure_cost_management"),
    }
