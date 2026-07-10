"""Azure Cache for Redis SKU specifications — loaded from data/redis_sku_specifications.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).resolve().parents[1] / "data" / "redis_sku_specifications.json"

_TIER_ALIASES = {
    "basic": "Basic",
    "standard": "Standard",
    "premium": "Premium",
    "enterprise": "Enterprise",
    "enterpriseflash": "EnterpriseFlash",
    "enterprise flash": "EnterpriseFlash",
    "flash": "EnterpriseFlash",
}


@lru_cache(maxsize=1)
def load_redis_sku_specifications() -> dict[str, Any]:
    if not _SPEC_PATH.is_file():
        return {}
    with _SPEC_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def normalize_redis_tier_name(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    key = text.lower().replace("_", "").replace("-", "")
    if key in _TIER_ALIASES:
        return _TIER_ALIASES[key]
    for alias, canonical in _TIER_ALIASES.items():
        if alias in key or key in alias:
            return canonical
    return text.title()


def tier_spec(tier_name: str | None) -> dict[str, Any]:
    specs = load_redis_sku_specifications()
    tiers = specs.get("tiers") or {}
    canonical = normalize_redis_tier_name(tier_name)
    return dict(tiers.get(canonical) or {})


def capacity_spec(tier_name: str | None, capacity: int | None) -> dict[str, Any]:
    """Return capacity unit metadata when tier + capacity index are known."""
    specs = load_redis_sku_specifications()
    units = specs.get("capacity_units") or {}
    tier = normalize_redis_tier_name(tier_name)
    if capacity is None:
        return {}
    prefix = {"Basic": "C", "Standard": "C", "Premium": "P"}.get(tier, "C")
    key = f"{prefix}{capacity}"
    return dict(units.get(key) or {})


def optimization_thresholds() -> dict[str, float]:
    specs = load_redis_sku_specifications()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def tier_supports_clustering(tier_name: str | None) -> bool:
    return bool(tier_spec(tier_name).get("clustering"))


def tier_supports_persistence(tier_name: str | None) -> bool:
    return bool(tier_spec(tier_name).get("persistence"))


def suggested_upgrade_tier(current_tier: str | None) -> str | None:
    paths = tier_spec(current_tier).get("upgrade_paths") or []
    return paths[0] if paths else None


def suggested_downgrade_tier(current_tier: str | None) -> str | None:
    paths = tier_spec(current_tier).get("downgrade_paths") or []
    return paths[0] if paths else None


def parse_redis_arm_sku(cache: dict[str, Any]) -> dict[str, Any]:
    """Normalize tier, capacity, and shard metadata from an ARM cache envelope."""
    sku = cache.get("sku") or {}
    props = cache.get("properties") or {}
    redis_config = props.get("redisConfiguration") or {}
    tier_raw = sku.get("family") or sku.get("name") or ""
    tier = normalize_redis_tier_name(tier_raw)
    try:
        capacity = int(sku.get("capacity") or 0)
    except (TypeError, ValueError):
        capacity = 0
    try:
        shard_count = int(props.get("shardCount") or 1)
    except (TypeError, ValueError):
        shard_count = 1
    maxmemory_policy = redis_config.get("maxmemoryPolicy") or redis_config.get("maxmemory-policy")
    rdb_enabled = str(redis_config.get("rdbBackupEnabled") or "").lower() == "true"
    aof_enabled = str(redis_config.get("aofBackupEnabled") or "").lower() == "true"
    cap_meta = capacity_spec(tier, capacity if capacity > 0 else None)
    return {
        "tier": tier,
        "tier_raw": tier_raw,
        "capacity": capacity,
        "shard_count": max(1, shard_count),
        "maxmemory_policy": maxmemory_policy,
        "rdb_enabled": rdb_enabled,
        "aof_enabled": aof_enabled,
        "persistence_enabled": rdb_enabled or aof_enabled,
        "memory_mb": cap_meta.get("memory_mb"),
        "max_connections": cap_meta.get("max_connections"),
        "clustering": shard_count > 1 or tier_supports_clustering(tier),
    }
