"""Azure Load Balancer specifications — loaded from data/load_balancer_metrics_thresholds.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).resolve().parents[1] / "data" / "load_balancer_metrics_thresholds.json"


@lru_cache(maxsize=1)
def load_load_balancer_specifications() -> dict[str, Any]:
    if not _SPEC_PATH.is_file():
        return {}
    with _SPEC_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def optimization_thresholds() -> dict[str, float]:
    specs = load_load_balancer_specifications()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def basic_sku_retirement_date() -> str:
    return str(load_load_balancer_specifications().get("basic_sku_retirement") or "2025-09-30")


def sku_spec(sku_name: str | None) -> dict[str, Any]:
    specs = load_load_balancer_specifications()
    skus = specs.get("skus") or {}
    key = (sku_name or "Standard").strip()
    return dict(skus.get(key) or skus.get("Standard") or {})


def parse_load_balancer_arm(lb: dict[str, Any]) -> dict[str, Any]:
    sku = lb.get("sku") or {}
    props = lb.get("properties") or {}
    sku_name = sku.get("name") or "Basic"
    backends = props.get("backendAddressPools") or []
    all_empty = True
    if backends:
        all_empty = all(
            not (pool.get("properties") or {}).get("backendIPConfigurations")
            and not (pool.get("properties") or {}).get("loadBalancerBackendAddresses")
            for pool in backends
        )
    meta = sku_spec(sku_name)
    return {
        "sku_name": sku_name,
        "backend_pool_count": len(backends),
        "all_backends_empty": all_empty,
        "sku_retiring": bool(meta.get("retiring")),
        "migrate_to_sku": meta.get("migrate_to") or "Standard",
    }
