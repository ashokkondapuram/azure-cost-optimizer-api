"""Shared engine runtime helpers — global config, filters, savings gates."""

from __future__ import annotations

from typing import Any

from app.optimizer.engine_config import GLOBAL_CONFIG_KEY
from app.optimizer.engine_filters import should_skip_resource
from app.optimizer.rules import DEFAULT_RULES, Rule
from app.optimizer.rule_overrides import apply_rule_overrides

COMMON_RULE_SETTINGS = ("min_monthly_savings_usd", "waste_score_multiplier", "evaluation_window_days")


def split_rule_overrides(rule_overrides: dict[str, dict] | None) -> tuple[dict[str, dict], dict[str, Any]]:
    """Separate per-rule overrides from subscription-wide filter config."""
    merged = dict(rule_overrides or {})
    global_cfg = dict(merged.pop(GLOBAL_CONFIG_KEY, None) or {})
    return merged, global_cfg


def filter_resources(resources: list[dict] | None, global_config: dict[str, Any] | None) -> list[dict]:
    if not resources:
        return []
    return [r for r in resources if not should_skip_resource(r, global_config)]


def filter_bucket_dict(buckets: dict[str, list], global_config: dict[str, Any] | None) -> dict[str, list]:
    """Apply tag/RG/type exclusions before metrics load and engine analysis."""
    return {key: filter_resources(items, global_config) for key, items in (buckets or {}).items()}


def passes_savings_gate(finding: Any, rules: dict[str, Rule]) -> bool:
    rule = rules.get(getattr(finding, "rule_id", ""))
    if not rule:
        return True
    min_savings = float(getattr(rule, "min_monthly_savings_usd", 0.0) or 0.0)
    savings = float(getattr(finding, "estimated_savings_usd", 0.0) or 0.0)
    if savings <= 0:
        return True
    return savings >= min_savings


def build_standard_rules(rule_overrides: dict[str, dict] | None = None) -> dict[str, Rule]:
    """Deep-copy default rules with optional per-rule overrides."""
    import copy

    rules: dict[str, Rule] = {}
    for rid, rule in DEFAULT_RULES.items():
        r = copy.deepcopy(rule)
        if rule_overrides and rid in rule_overrides:
            apply_rule_overrides(r, rule_overrides[rid])
        rules[rid] = r
    return rules
