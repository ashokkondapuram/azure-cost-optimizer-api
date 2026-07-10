"""Managed disk analysis configuration — owned by compute-disk IT service."""

from __future__ import annotations

import copy
from dataclasses import fields
from functools import lru_cache
from typing import Any

from it_services.compute_disk.managed_disk_catalog import load_disk_specifications
from app.optimizer.advanced_rules import AdvancedRule, Category, Severity


def disk_rule_ids() -> list[str]:
    spec = load_disk_specifications()
    rules = spec.get("analysis_rules") or {}
    return sorted(rules.keys())


@lru_cache(maxsize=1)
def supplemental_disk_rules() -> dict[str, AdvancedRule]:
    """Build AdvancedRule instances for disk rules defined in JSON but not in ADVANCED_RULES."""
    from app.optimizer.advanced_rules import ADVANCED_RULES

    spec = load_disk_specifications()
    raw = spec.get("analysis_rules") or {}
    out: dict[str, AdvancedRule] = {}
    for rule_id, cfg in raw.items():
        if rule_id in ADVANCED_RULES:
            continue
        if not isinstance(cfg, dict):
            continue
        out[rule_id] = _rule_from_json(rule_id, cfg)
    return out


def hydrate_disk_rules(rules: dict[str, Any]) -> None:
    """Merge JSON-defined disk rules into an engine rules map (in place)."""
    for rule_id, rule in supplemental_disk_rules().items():
        if rule_id not in rules:
            rules[rule_id] = copy.deepcopy(rule)


def extended_disk_spec_payload() -> dict[str, Any]:
    """Full disk analysis JSON for API consumers."""
    spec = load_disk_specifications()
    from app.optimizer.advanced_rules import ADVANCED_RULES
    from app.optimizer.rule_catalog import RULE_MANIFEST

    applied: list[dict[str, Any]] = []
    for rule_id in disk_rule_ids():
        cfg = (spec.get("analysis_rules") or {}).get(rule_id) or {}
        catalog = RULE_MANIFEST.get(rule_id) or {}
        advanced = ADVANCED_RULES.get(rule_id) or supplemental_disk_rules().get(rule_id)
        applied.append({
            "rule_id": rule_id,
            "engine": catalog.get("engine", "extended"),
            "component": catalog.get("component", "Managed Disks"),
            "enabled": bool(getattr(advanced, "enabled", True)) if advanced else True,
            "savings_basis": cfg.get("savings_basis", "azure_billed_mtd"),
            "config": cfg,
        })
    return {
        "canonical_type": "compute/disk",
        "schema_version": spec.get("schema_version"),
        "spec": spec,
        "analysis_rules": applied,
        "cost_source": "azure_cost_management_pretax",
    }


def _rule_from_json(rule_id: str, cfg: dict[str, Any]) -> AdvancedRule:
    severity = Severity[str(cfg.get("severity", "MEDIUM").upper())]
    category = Category[str(cfg.get("category", "COMPUTE").upper())]
    kwargs: dict[str, Any] = {
        "id": rule_id,
        "name": str(cfg.get("name") or rule_id.replace("_", " ").title()),
        "description": str(cfg.get("description") or ""),
        "category": category,
        "severity": severity,
        "enabled": bool(cfg.get("enabled", True)),
    }
    field_names = {f.name for f in fields(AdvancedRule)}
    for key, value in (cfg.get("thresholds") or {}).items():
        if key in field_names:
            kwargs[key] = value
    if "min_monthly_savings_usd" in cfg:
        kwargs["min_monthly_savings_usd"] = float(cfg["min_monthly_savings_usd"])
    return AdvancedRule(**kwargs)
