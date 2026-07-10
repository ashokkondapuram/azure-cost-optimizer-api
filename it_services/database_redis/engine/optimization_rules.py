"""Redis Cache optimization decision rules — metrics + SKU intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.cost_utils import savings_from_factor
from app.azure_retail_pricing import estimate_redis_tier_transition
from app.pricing.savings_calculator import savings_from_retail_or_none
from app.redis_sku_catalog import (
    optimization_thresholds,
    parse_redis_arm_sku,
    suggested_downgrade_tier,
    suggested_upgrade_tier,
    tier_supports_persistence,
)
from app.resource_utilization import (
    confidence_with_monitor,
    fact_value,
    is_low_memory,
    make_check,
    memory_pct,
    metrics_block_rightsize,
    monitor_evidence,
    structured_evidence,
    utilization_gate,
)


@dataclass(frozen=True)
class RedisFindingDraft:
    rule_id: str
    detail: str
    recommendation: str
    savings: float
    waste_score: int
    confidence: int
    priority: str
    impact: str
    evidence: dict[str, Any]


def _thresholds(rule: Any) -> dict[str, float]:
    defaults = optimization_thresholds()
    return {
        "memory_pressure_pct": float(getattr(rule, "redis_memory_pressure_pct", defaults.get("memory_pressure_pct", 85.0))),
        "memory_low_pct": float(getattr(rule, "redis_low_utilization_pct", defaults.get("memory_low_utilization_pct", 30.0))),
        "server_load_low_pct": float(getattr(rule, "redis_server_load_low_pct", defaults.get("server_load_low_pct", 20.0))),
        "hit_ratio_poor_pct": float(getattr(rule, "redis_hit_ratio_poor_pct", defaults.get("hit_ratio_poor_pct", 50.0))),
        "cluster_ops_threshold": float(getattr(rule, "redis_cluster_ops_threshold", defaults.get("cluster_unnecessary_ops_per_sec", 50000.0))),
        "idle_ops_threshold": float(getattr(rule, "redis_idle_ops_threshold", defaults.get("idle_ops_per_sec", 0.0))),
    }


def _hit_ratio_pct(cache: dict[str, Any]) -> float | None:
    direct = fact_value(cache, "cache_hit_rate")
    if direct is not None:
        return direct
    hits = fact_value(cache, "cache_hits")
    misses = fact_value(cache, "cache_misses")
    if hits is None and misses is None:
        miss_rate = fact_value(cache, "cache_miss_rate_pct")
        if miss_rate is not None:
            return max(0.0, min(100.0, 100.0 - miss_rate))
        return None
    total = (hits or 0.0) + (misses or 0.0)
    if total <= 0:
        return None
    return round((hits or 0.0) / total * 100.0, 2)


def _redis_metric_evidence(cache: dict[str, Any], sku_ctx: dict[str, Any], extra: dict | None = None) -> dict[str, Any]:
    mem = memory_pct(cache)
    ops = fact_value(cache, "ops_per_sec")
    hit = _hit_ratio_pct(cache)
    payload = {
        "tier": sku_ctx.get("tier"),
        "capacity": sku_ctx.get("capacity"),
        "shard_count": sku_ctx.get("shard_count"),
        "memory_pct": round(mem, 2) if mem is not None else None,
        "ops_per_sec": ops,
        "cache_hit_rate_pct": hit,
        "server_load_pct": fact_value(cache, "server_load_pct"),
        "evicted_keys": fact_value(cache, "evicted_keys"),
        "connected_clients": fact_value(cache, "connected_clients"),
        "maxmemory_policy": sku_ctx.get("maxmemory_policy"),
        "memory_mb": sku_ctx.get("memory_mb"),
        "max_connections": sku_ctx.get("max_connections"),
    }
    base = monitor_evidence(cache, payload)
    if extra:
        base.update(extra)
    return base


def _tier_pricing_savings(
    cache: dict[str, Any],
    sku_ctx: dict[str, Any],
    monthly: float,
    *,
    suggested_tier: str,
    suggested_capacity: int | None = None,
) -> tuple[float, dict[str, Any]]:
    cap = suggested_capacity if suggested_capacity is not None else sku_ctx.get("capacity") or 1
    pricing = estimate_redis_tier_transition(
        cache.get("location") or "",
        sku_ctx.get("tier") or "Premium",
        int(sku_ctx.get("capacity") or 1),
        suggested_tier,
        int(cap),
        actual_monthly_cost=monthly if monthly > 0 else None,
    )
    savings = savings_from_retail_or_none(pricing)
    if savings is None and monthly > 0:
        savings = savings_from_factor(monthly, 0.35)
    return float(savings or 0.0), pricing


def evaluate_redis_idle(
    cache: dict[str, Any],
    sku_ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> RedisFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    if not utilization_gate(cache, "ops_per_sec", allow_inventory_only=False):
        return None
    ops = fact_value(cache, "ops_per_sec")
    thresholds = _thresholds(rule)
    if ops is None or ops > thresholds["idle_ops_threshold"]:
        return None
    name = cache.get("name") or ""
    return RedisFindingDraft(
        rule_id="REDIS_IDLE_DETECTION",
        detail=f"Redis cache '{name}' shows zero operations per second in Azure Monitor over the evaluation window.",
        recommendation="Delete the cache if unused, or export data and migrate workloads before decommissioning.",
        savings=monthly if monthly > 0 else 0.0,
        waste_score=78,
        confidence=confidence_with_monitor(88, cache, required_keys=("ops_per_sec",)),
        priority="P2",
        impact="Eliminates spend on idle cache instance",
        evidence=_redis_metric_evidence(cache, sku_ctx, {"determination": "idle_zero_ops"}),
    )


def evaluate_redis_memory_pressure(
    cache: dict[str, Any],
    sku_ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> RedisFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    if not utilization_gate(cache, "memory_pct", allow_inventory_only=False):
        return None
    mem = memory_pct(cache)
    evicted = fact_value(cache, "evicted_keys") or 0.0
    thresholds = _thresholds(rule)
    pressure = mem is not None and mem >= thresholds["memory_pressure_pct"]
    evicting = evicted > 0
    if not pressure and not evicting:
        return None
    name = cache.get("name") or ""
    upgrade_tier = suggested_upgrade_tier(sku_ctx.get("tier")) or sku_ctx.get("tier") or "Premium"
    suggested_cap = max(1, int(sku_ctx.get("capacity") or 1) + 1)
    savings = 0.0
    detail = f"Redis '{name}' shows memory pressure"
    if mem is not None:
        detail += f" ({mem:.1f}% used)"
    if evicting:
        detail += f" with {int(evicted):,} evicted keys"
    detail += "."
    recommendation = (
        f"Upgrade to {upgrade_tier} C{suggested_cap} (or next size up) to add ~25% headroom. "
        "Review eviction policy and TTL settings if memory is available but evictions persist."
    )
    return RedisFindingDraft(
        rule_id="REDIS_MEMORY_PRESSURE",
        detail=detail,
        recommendation=recommendation,
        savings=savings,
        waste_score=82 if (mem or 0) >= float(optimization_thresholds().get("upgrade_urgent_memory_pct", 90)) else 70,
        confidence=confidence_with_monitor(76, cache, required_keys=("memory_pct",)),
        priority="P1" if evicting or (mem or 0) >= 90 else "P2",
        impact="Prevents data loss from evictions and latency spikes",
        evidence=_redis_metric_evidence(
            cache,
            sku_ctx,
            {
                "determination": "memory_pressure",
                "suggested_tier": upgrade_tier,
                "suggested_capacity": suggested_cap,
            },
        ),
    )


def evaluate_redis_low_utilization(
    cache: dict[str, Any],
    sku_ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> RedisFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    if metrics_block_rightsize(cache):
        return None
    if not utilization_gate(cache, "memory_pct", allow_inventory_only=False):
        return None
    thresholds = _thresholds(rule)
    mem = memory_pct(cache)
    load = fact_value(cache, "server_load_pct")
    low_mem = is_low_memory(cache, threshold=thresholds["memory_low_pct"])
    if low_mem is not True:
        return None
    if load is not None and load >= thresholds["server_load_low_pct"]:
        return None
    evicted = fact_value(cache, "evicted_keys") or 0.0
    if evicted > 0:
        return None
    downgrade_tier = suggested_downgrade_tier(sku_ctx.get("tier"))
    if not downgrade_tier and (sku_ctx.get("capacity") or 0) <= 1:
        return None
    suggested_cap = max(1, int(sku_ctx.get("capacity") or 1) // 2) or 1
    target_tier = downgrade_tier or sku_ctx.get("tier") or "Standard"
    savings, pricing = _tier_pricing_savings(
        cache, sku_ctx, monthly, suggested_tier=target_tier, suggested_capacity=suggested_cap,
    )
    min_savings = float(getattr(rule, "min_monthly_savings_usd", 0.0) or 0.0)
    if savings > 0 and savings < min_savings:
        return None
    name = cache.get("name") or ""
    detail = f"Redis '{name}' is underutilized"
    if mem is not None:
        detail += f" ({mem:.1f}% memory used)"
    if load is not None:
        detail += f" with {load:.1f}% server load"
    detail += "."
    return RedisFindingDraft(
        rule_id="REDIS_LOW_UTILIZATION",
        detail=detail,
        recommendation=(
            f"Downgrade to {target_tier} C{suggested_cap} after validating no growth spike is expected. "
            "Plan migration to Azure Managed Redis before Sept 30, 2028 retirement."
        ),
        savings=savings,
        waste_score=56,
        confidence=confidence_with_monitor(72, cache, required_keys=("memory_pct",)),
        priority="P3",
        impact="Cache SKU right-sizing for sustained low utilization",
        evidence=structured_evidence(
            cache,
            determination="low_utilization",
            summary="Redis memory and server load are consistently low.",
            checks=[
                make_check("Memory utilization", mem, f"< {thresholds['memory_low_pct']}%", passed=True),
                make_check("Server load", load, f"< {thresholds['server_load_low_pct']}%", passed=load is None or load < thresholds["server_load_low_pct"]),
            ],
            extra={**pricing, **sku_ctx},
        ),
    )


def evaluate_redis_hit_ratio(
    cache: dict[str, Any],
    sku_ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> RedisFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    hit = _hit_ratio_pct(cache)
    if hit is None:
        return None
    thresholds = _thresholds(rule)
    if hit > thresholds["hit_ratio_poor_pct"]:
        return None
    mem = memory_pct(cache)
    name = cache.get("name") or ""
    if mem is not None and mem < 70:
        recommendation = (
            "Review eviction policy (maxmemory-policy) and TTL settings. "
            "Keys without TTL may be evicted under volatile-lru policies."
        )
        impact = "Cache effectiveness — configuration tuning"
    else:
        recommendation = (
            "Upgrade cache size or tier to increase working set capacity. "
            "Validate dataset size vs. provisioned memory."
        )
        impact = "Cache effectiveness — capacity increase likely needed"
    return RedisFindingDraft(
        rule_id="REDIS_HIT_RATIO_POOR",
        detail=f"Redis '{name}' cache hit ratio is {hit:.1f}% (target > {thresholds['hit_ratio_poor_pct']}%).",
        recommendation=recommendation,
        savings=0.0,
        waste_score=48,
        confidence=confidence_with_monitor(70, cache, required_keys=("cache_hits",)),
        priority="P3",
        impact=impact,
        evidence=_redis_metric_evidence(cache, sku_ctx, {"determination": "poor_hit_ratio"}),
    )


def evaluate_redis_cluster_unnecessary(
    cache: dict[str, Any],
    sku_ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> RedisFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    shards = int(sku_ctx.get("shard_count") or 1)
    if shards > 1:
        return None
    if not utilization_gate(cache, "ops_per_sec", allow_inventory_only=False):
        return None
    ops = fact_value(cache, "ops_per_sec")
    thresholds = _thresholds(rule)
    if ops is None or ops > thresholds["cluster_ops_threshold"]:
        return None
    tier = sku_ctx.get("tier") or ""
    if tier not in ("Premium", "Enterprise", "EnterpriseFlash"):
        return None
    name = cache.get("name") or ""
    savings, pricing = _tier_pricing_savings(cache, sku_ctx, monthly, suggested_tier="Standard")
    return RedisFindingDraft(
        rule_id="REDIS_CLUSTER_UNNECESSARY",
        detail=(
            f"Redis '{name}' runs on {tier} with a single shard and {ops:,.0f} ops/sec — "
            "clustering may add cost without throughput benefit."
        ),
        recommendation=(
            "Consider Standard tier without clustering for this workload, or consolidate caches. "
            "Validate failover and persistence requirements before changing tier."
        ),
        savings=savings,
        waste_score=52,
        confidence=confidence_with_monitor(65, cache, required_keys=("ops_per_sec",)),
        priority="P3",
        impact="Simplifies cache topology and may reduce tier cost",
        evidence=_redis_metric_evidence(cache, sku_ctx, {**pricing, "determination": "cluster_unnecessary"}),
    )


def evaluate_redis_persistence(
    cache: dict[str, Any],
    sku_ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> RedisFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    tier = sku_ctx.get("tier") or ""
    if not tier_supports_persistence(tier):
        return None
    if not sku_ctx.get("persistence_enabled"):
        return None
    name = cache.get("name") or ""
    modes = []
    if sku_ctx.get("rdb_enabled"):
        modes.append("RDB")
    if sku_ctx.get("aof_enabled"):
        modes.append("AOF")
    mode_text = " and ".join(modes) or "persistence"
    return RedisFindingDraft(
        rule_id="REDIS_PERSISTENCE_REVIEW",
        detail=f"Redis '{name}' on {tier} has {mode_text} persistence enabled.",
        recommendation=(
            "Review whether persistence is required for this workload. RDB has lower overhead than AOF. "
            "Use Import/Export for backups — avoid soft-delete on storage accounts linked to persistence."
        ),
        savings=savings_from_factor(monthly, 0.1) if monthly > 0 else 0.0,
        waste_score=40,
        confidence=62,
        priority="P3",
        impact="Persistence storage and backup cost review",
        evidence=_redis_metric_evidence(
            cache,
            sku_ctx,
            {"determination": "persistence_review", "persistence_modes": modes},
        ),
    )


def evaluate_redis_tier_review(
    cache: dict[str, Any],
    sku_ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> RedisFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    tier = (sku_ctx.get("tier") or "").lower()
    capacity = int(sku_ctx.get("capacity") or 0)
    if "premium" not in tier and capacity < int(getattr(rule, "redis_premium_min_capacity", 1)):
        return None
    shards = int(sku_ctx.get("shard_count") or 1)
    policy = sku_ctx.get("maxmemory_policy") or "unknown"
    if shards <= 1 and policy in (None, "", "unknown", "allkeys-lru"):
        return None
    name = cache.get("name") or ""
    savings, pricing = _tier_pricing_savings(cache, sku_ctx, monthly, suggested_tier="Standard")
    min_savings = float(getattr(rule, "min_monthly_savings_usd", 0.0) or 0.0)
    if savings > 0 and savings < min_savings:
        return None
    return RedisFindingDraft(
        rule_id="REDIS_TIER_REVIEW",
        detail=(
            f"Redis '{name}' uses {sku_ctx.get('tier')} C{capacity} with {shards} shard(s) "
            f"and eviction policy '{policy}'."
        ),
        recommendation=(
            "Validate shard count and maxmemory-policy against workload shape. "
            "Reduce shards or move to Standard if HA without clustering is sufficient."
        ),
        savings=savings,
        waste_score=50,
        confidence=60,
        priority="P3",
        impact="Tier, shard, and eviction policy alignment",
        evidence=_redis_metric_evidence(cache, sku_ctx, {**pricing, "determination": "tier_shard_review"}),
    )


def evaluate_redis_rightsizing(
    cache: dict[str, Any],
    sku_ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> RedisFindingDraft | None:
    """Premium capacity downgrade when memory is low (legacy REDIS_RIGHTSIZE_EXTENDED path)."""
    if not rule or not rule.enabled:
        return None
    tier = (sku_ctx.get("tier") or "").lower()
    capacity = int(sku_ctx.get("capacity") or 0)
    if "premium" not in tier or capacity < int(getattr(rule, "redis_premium_min_capacity", 1)):
        return None
    if metrics_block_rightsize(cache):
        return None
    if not utilization_gate(cache, "memory_pct", allow_inventory_only=False):
        return None
    if is_low_memory(cache, threshold=35.0) is not True:
        return None
    ops = fact_value(cache, "ops_per_sec")
    if ops is not None and ops >= 100:
        return None
    suggested_cap = max(1, capacity // 2)
    savings, pricing = _tier_pricing_savings(
        cache, sku_ctx, monthly, suggested_tier="Standard", suggested_capacity=suggested_cap,
    )
    min_savings = float(getattr(rule, "min_monthly_savings_usd", 0.0) or 0.0)
    if savings > 0 and savings < min_savings:
        return None
    mem = memory_pct(cache)
    name = cache.get("name") or ""
    detail = f"Redis '{name}' uses Premium capacity {capacity}."
    if mem is not None:
        detail += f" Memory utilization is {mem:.1f}% in Azure Monitor."
    return RedisFindingDraft(
        rule_id="REDIS_RIGHTSIZE_EXTENDED",
        detail=detail,
        recommendation=(
            "Review memory pressure metrics and test Standard tier for non-production workloads. "
            "Plan migration to Azure Managed Redis before retirement on Sept 30, 2028."
        ),
        savings=savings,
        waste_score=54,
        confidence=confidence_with_monitor(68, cache, required_keys=("memory_pct",)),
        priority="P3",
        impact="Cache SKU right-sizing opportunity",
        evidence=monitor_evidence(cache, {"tier": tier, "capacity": capacity, **pricing}),
    )
