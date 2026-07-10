"""Azure NSG flow log costs — loaded from data/nsg_flow_log_costs.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).resolve().parents[1] / "data" / "nsg_flow_log_costs.json"


@lru_cache(maxsize=1)
def load_nsg_specifications() -> dict[str, Any]:
    if not _SPEC_PATH.is_file():
        return {}
    with _SPEC_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def optimization_thresholds() -> dict[str, float]:
    specs = load_nsg_specifications()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def pricing_config() -> dict[str, Any]:
    return dict(load_nsg_specifications().get("pricing") or {})


def flow_log_cost_per_gb() -> float:
    pricing = pricing_config()
    return float(pricing.get("flow_log_ingestion_per_gb_usd") or 0.50) + float(pricing.get("storage_per_gb_month_usd") or 0.02)


def parse_nsg_arm(nsg: dict[str, Any]) -> dict[str, Any]:
    props = nsg.get("properties") or {}
    facts = nsg.get("_technical_facts") or {}
    subnets = props.get("subnets") or []
    nics = props.get("networkInterfaces") or []
    rules = props.get("securityRules") or []
    return {
        "subnet_count": len(subnets),
        "nic_count": len(nics),
        "rule_count": int(facts.get("rule_count") if facts.get("rule_count") is not None else len(rules)),
        "flow_log_bytes": facts.get("flow_log_bytes"),
        "flow_log_enabled": facts.get("flow_log_enabled"),
    }
