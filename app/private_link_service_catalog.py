"""Azure Private Link Service cost model — loaded from data/private_link_service_cost_model.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).resolve().parents[1] / "data" / "private_link_service_cost_model.json"


@lru_cache(maxsize=1)
def load_private_link_service_specifications() -> dict[str, Any]:
    if not _SPEC_PATH.is_file():
        return {}
    with _SPEC_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def optimization_thresholds() -> dict[str, float]:
    specs = load_private_link_service_specifications()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def pricing_config() -> dict[str, Any]:
    return dict(load_private_link_service_specifications().get("pricing") or {})


def nat_port_capacity() -> int:
    return int(pricing_config().get("nat_ports_per_instance") or 64000)


def hourly_baseline_usd() -> float:
    return float(pricing_config().get("hourly_usd_baseline") or 0.01)


def parse_private_link_service_arm(service: dict[str, Any]) -> dict[str, Any]:
    props = service.get("properties") or {}
    facts = service.get("_technical_facts") or {}
    connections = props.get("privateEndpointConnections") or []
    return {
        "connection_count": int(facts.get("connection_count") if facts.get("connection_count") is not None else len(connections)),
        "fqdn_count": len(props.get("fqdns") or []),
        "nat_port_capacity": nat_port_capacity(),
    }
