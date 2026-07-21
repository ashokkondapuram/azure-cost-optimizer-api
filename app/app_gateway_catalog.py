"""Azure Application Gateway specifications — loaded from data/app_gateway_metrics_thresholds.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).resolve().parents[1] / "data" / "app_gateway_metrics_thresholds.json"


@lru_cache(maxsize=1)
def load_app_gateway_specifications() -> dict[str, Any]:
    if not _SPEC_PATH.is_file():
        return {}
    with _SPEC_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def optimization_thresholds() -> dict[str, float]:
    specs = load_app_gateway_specifications()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def tier_spec(tier_name: str | None) -> dict[str, Any]:
    specs = load_app_gateway_specifications()
    tiers = specs.get("sku_tiers") or {}
    key = (tier_name or "Standard_v2").strip()
    return dict(tiers.get(key) or tiers.get("Standard_v2") or {})


def parse_app_gateway_arm(gateway: dict[str, Any]) -> dict[str, Any]:
    sku = gateway.get("sku") or {}
    props = gateway.get("properties") or {}
    tier = sku.get("tier") or sku.get("name") or "Standard_v2"
    capacity = int(sku.get("capacity") or 1)
    meta = tier_spec(tier)
    cu_per_unit = float(meta.get("cu_per_capacity_unit") or 100)
    return {
        "sku_tier": tier,
        "capacity": capacity,
        "provisioned_cu": capacity * cu_per_unit,
        "autoscale_enabled": bool((props.get("autoscaleConfiguration") or {}).get("minCapacity") is not None),
    }
