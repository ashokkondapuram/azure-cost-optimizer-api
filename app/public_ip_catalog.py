"""Azure Public IP specifications — loaded from data/public_ip_metrics_thresholds.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).resolve().parents[1] / "data" / "public_ip_metrics_thresholds.json"


@lru_cache(maxsize=1)
def load_public_ip_specifications() -> dict[str, Any]:
    if not _SPEC_PATH.is_file():
        return {}
    with _SPEC_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def optimization_thresholds() -> dict[str, float]:
    specs = load_public_ip_specifications()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def sku_spec(sku_name: str | None) -> dict[str, Any]:
    specs = load_public_ip_specifications()
    skus = specs.get("skus") or {}
    key = (sku_name or "Standard").strip()
    return dict(skus.get(key) or skus.get("Standard") or {})


def basic_sku_retirement_date() -> str:
    return str(load_public_ip_specifications().get("basic_sku_retirement") or "2025-09-30")


def parse_public_ip_arm(ip: dict[str, Any]) -> dict[str, Any]:
    sku = ip.get("sku") or {}
    props = ip.get("properties") or {}
    sku_name = sku.get("name") or sku.get("tier") or "Standard"
    tier = sku.get("tier") or sku_name
    assoc = props.get("ipConfiguration") or props.get("natGateway")
    alloc = props.get("publicIPAllocationMethod") or ""
    meta = sku_spec(sku_name)
    return {
        "sku_name": sku_name,
        "sku_tier": tier,
        "allocation": alloc,
        "is_associated": bool(assoc),
        "ip_address": props.get("ipAddress"),
        "sku_retiring": bool(meta.get("retiring")),
        "migrate_to_sku": meta.get("migrate_to") or "Standard",
        "zone_redundant": bool(meta.get("zone_redundant")),
    }
