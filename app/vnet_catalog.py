"""Azure Virtual Network service costs — loaded from data/vnet_service_costs.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).resolve().parents[1] / "data" / "vnet_service_costs.json"


@lru_cache(maxsize=1)
def load_vnet_specifications() -> dict[str, Any]:
    if not _SPEC_PATH.is_file():
        return {}
    with _SPEC_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def optimization_thresholds() -> dict[str, float]:
    specs = load_vnet_specifications()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def integrated_service_costs() -> dict[str, Any]:
    return dict(load_vnet_specifications().get("integrated_services") or {})


def parse_vnet_arm(vnet: dict[str, Any]) -> dict[str, Any]:
    props = vnet.get("properties") or {}
    facts = vnet.get("_technical_facts") or {}
    subnets = props.get("subnets") or []
    peerings = props.get("virtualNetworkPeerings") or []
    empty_subnets = 0
    for subnet in subnets:
        sp = subnet.get("properties") or {}
        prefix = sp.get("addressPrefix") or ""
        if not sp.get("ipConfigurations") and not sp.get("serviceEndpoints") and not sp.get("delegations"):
            if prefix:
                empty_subnets += 1
    return {
        "subnet_count": int(facts.get("subnet_count") if facts.get("subnet_count") is not None else len(subnets)),
        "peering_count": int(facts.get("peering_count") if facts.get("peering_count") is not None else len(peerings)),
        "empty_subnet_count": empty_subnets,
    }
