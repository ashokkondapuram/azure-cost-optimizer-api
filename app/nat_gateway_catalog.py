"""Azure NAT Gateway specifications — loaded from data/nat_gateway_metrics_thresholds.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).resolve().parents[1] / "data" / "nat_gateway_metrics_thresholds.json"


@lru_cache(maxsize=1)
def load_nat_gateway_specifications() -> dict[str, Any]:
    if not _SPEC_PATH.is_file():
        return {}
    with _SPEC_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def optimization_thresholds() -> dict[str, float]:
    specs = load_nat_gateway_specifications()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def sku_spec(sku_name: str | None) -> dict[str, Any]:
    specs = load_nat_gateway_specifications()
    skus = specs.get("skus") or {}
    key = (sku_name or "Standard").strip()
    if key in skus:
        return dict(skus[key])
    if key.replace("_", "") == "StandardV2":
        return dict(skus.get("StandardV2") or {})
    return dict(skus.get("Standard") or {})


def snat_capacity_for_gateway(nat: dict[str, Any], ctx: dict[str, Any] | None = None) -> int:
    """Max SNAT ports based on attached public IP count."""
    ctx = ctx or parse_nat_gateway_arm(nat)
    specs = sku_spec(ctx.get("sku_name"))
    ports_per_ip = int(specs.get("snat_ports_per_ip") or 64512)
    ip_count = max(1, int(ctx.get("public_ip_count") or 1))
    return ports_per_ip * min(ip_count, int(specs.get("max_public_ips") or 16))


def parse_nat_gateway_arm(nat: dict[str, Any]) -> dict[str, Any]:
    sku = nat.get("sku") or {}
    props = nat.get("properties") or {}
    sku_name = sku.get("name") or "Standard"
    subnets = props.get("subnets") or []
    public_ips = props.get("publicIpAddresses") or []
    meta = sku_spec(sku_name)
    return {
        "sku_name": sku_name,
        "subnet_count": len(subnets),
        "public_ip_count": len(public_ips),
        "max_throughput_gbps": float(meta.get("max_throughput_gbps") or 50),
        "zone_redundant": bool(meta.get("zone_redundant")),
    }
