"""Azure Private Endpoint cost model — loaded from data/private_endpoint_cost_model.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).resolve().parents[1] / "data" / "private_endpoint_cost_model.json"


@lru_cache(maxsize=1)
def load_private_endpoint_specifications() -> dict[str, Any]:
    if not _SPEC_PATH.is_file():
        return {}
    with _SPEC_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def optimization_thresholds() -> dict[str, float]:
    specs = load_private_endpoint_specifications()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def pricing_config() -> dict[str, Any]:
    return dict(load_private_endpoint_specifications().get("pricing") or {})


def hourly_baseline_usd() -> float:
    return float(pricing_config().get("hourly_usd_baseline") or 0.01)


def parse_private_endpoint_arm(endpoint: dict[str, Any]) -> dict[str, Any]:
    props = endpoint.get("properties") or {}
    facts = endpoint.get("_technical_facts") or {}
    connections = props.get("privateLinkServiceConnections") or props.get("manualPrivateLinkServiceConnections") or []
    state = str(facts.get("connection_state") or "").lower()
    if not state and connections:
        state = str(((connections[0] or {}).get("properties") or {}).get("privateLinkServiceConnectionState", {}).get("status") or "").lower()
    return {
        "connection_state": state,
        "target_resource_id": facts.get("target_resource_id"),
        "dns_zone_group_count": int(facts.get("dns_zone_group_count") or len(props.get("privateDnsZoneGroups") or [])),
        "subnet_id": ((props.get("subnet") or {}).get("id") or ""),
    }
