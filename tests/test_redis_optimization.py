"""Tests for Redis cache optimization engine."""

from __future__ import annotations

from app.optimizer.advanced_rules import ADVANCED_RULES
from app.optimizer.resource_engines.database.redis.optimization_rules import (
    evaluate_redis_cluster_unnecessary,
    evaluate_redis_hit_ratio,
    evaluate_redis_idle,
    evaluate_redis_low_utilization,
    evaluate_redis_memory_pressure,
    evaluate_redis_persistence,
    evaluate_redis_tier_review,
)
from app.optimizer.resource_engines.database.redis.analysis import analyze_redis
from app.redis_sku_catalog import load_redis_sku_specifications, parse_redis_arm_sku


class _FakeEngine:
    def __init__(self):
        self.rules = ADVANCED_RULES

    def _extract_rg(self, rid: str) -> str:
        parts = (rid or "").split("/")
        if "resourceGroups" in parts:
            idx = parts.index("resourceGroups")
            return parts[idx + 1] if idx + 1 < len(parts) else ""
        return ""

    def _finding(self, **kwargs):
        from datetime import datetime, timezone
        from app.optimizer.core.finding import ExtendedFinding
        rule = kwargs.pop("rule")
        resource = kwargs.get("resource") or {}
        rid = resource.get("id") or ""
        savings = float(kwargs.get("savings", 0) or 0)
        return ExtendedFinding(
            rule_id=rule.id,
            rule_name=rule.name,
            category=rule.category.value,
            severity=rule.severity.value,
            subscription_id=kwargs.get("subscription_id", ""),
            resource_id=rid,
            resource_name=resource.get("name") or "",
            resource_type=resource.get("type") or "database/redis",
            resource_group=self._extract_rg(rid),
            location=resource.get("location") or "",
            detail=kwargs.get("detail", ""),
            recommendation=kwargs.get("recommendation", ""),
            estimated_savings_usd=round(savings, 2),
            annualized_savings_usd=round(savings * 12, 2),
            waste_score=kwargs.get("waste_score", 0),
            confidence_score=kwargs.get("confidence", 0),
            action_priority=kwargs.get("priority", "P3"),
            impact=kwargs.get("impact", ""),
            evidence=kwargs.get("evidence") or {},
            tags=resource.get("tags") or {},
            detected_at=datetime.now(timezone.utc).isoformat(),
        )


def _cache(
    *,
    name: str = "cache1",
    tier: str = "Premium",
    capacity: int = 2,
    shards: int = 1,
    facts: dict | None = None,
    redis_config: dict | None = None,
) -> dict:
    props = {
        "provisioningState": "Succeeded",
        "shardCount": shards,
        "redisConfiguration": redis_config or {},
    }
    row = {
        "id": f"/subscriptions/s/resourceGroups/rg/providers/Microsoft.Cache/redis/{name}",
        "name": name,
        "location": "canadacentral",
        "sku": {"family": tier, "capacity": capacity},
        "properties": props,
    }
    if facts:
        row["_technical_facts"] = {**facts, "data_source": "azure_monitor"}
    return row


def test_redis_sku_specifications_loads():
    specs = load_redis_sku_specifications()
    assert specs.get("schema_version") == 1
    assert "Basic" in specs.get("tiers", {})
    assert "Premium" in specs.get("tiers", {})


def test_parse_redis_arm_sku():
    ctx = parse_redis_arm_sku(_cache(tier="Premium", capacity=2, shards=1))
    assert ctx["tier"] == "Premium"
    assert ctx["capacity"] == 2
    assert ctx["shard_count"] == 1


def test_idle_detection_zero_ops():
    cache = _cache(facts={"ops_per_sec": 0.0, "memory_pct": 5.0})
    sku = parse_redis_arm_sku(cache)
    draft = evaluate_redis_idle(cache, sku, 120.0, ADVANCED_RULES["REDIS_IDLE_DETECTION"])
    assert draft is not None
    assert draft.rule_id == "REDIS_IDLE_DETECTION"
    assert draft.savings == 120.0


def test_memory_pressure_high_utilization():
    cache = _cache(facts={"memory_pct": 88.0, "evicted_keys": 12.0})
    sku = parse_redis_arm_sku(cache)
    draft = evaluate_redis_memory_pressure(cache, sku, 80.0, ADVANCED_RULES["REDIS_MEMORY_PRESSURE"])
    assert draft is not None
    assert draft.rule_id == "REDIS_MEMORY_PRESSURE"
    assert draft.priority == "P1"


def test_low_utilization_downgrade_candidate():
    cache = _cache(
        tier="Premium",
        capacity=4,
        facts={"memory_pct": 18.0, "server_load_pct": 8.0, "evicted_keys": 0.0, "ops_per_sec": 20.0},
    )
    sku = parse_redis_arm_sku(cache)
    draft = evaluate_redis_low_utilization(cache, sku, 200.0, ADVANCED_RULES["REDIS_LOW_UTILIZATION"])
    assert draft is not None
    assert draft.rule_id == "REDIS_LOW_UTILIZATION"


def test_poor_hit_ratio():
    cache = _cache(facts={"cache_hits": 100.0, "cache_misses": 200.0, "memory_pct": 55.0})
    sku = parse_redis_arm_sku(cache)
    draft = evaluate_redis_hit_ratio(cache, sku, 50.0, ADVANCED_RULES["REDIS_HIT_RATIO_POOR"])
    assert draft is not None
    assert "33.3" in draft.detail or "33" in draft.detail


def test_cluster_unnecessary_single_shard_low_ops():
    cache = _cache(
        tier="Premium",
        capacity=2,
        shards=1,
        facts={"ops_per_sec": 1200.0, "memory_pct": 40.0},
    )
    sku = parse_redis_arm_sku(cache)
    draft = evaluate_redis_cluster_unnecessary(cache, sku, 90.0, ADVANCED_RULES["REDIS_CLUSTER_UNNECESSARY"])
    assert draft is not None
    assert draft.rule_id == "REDIS_CLUSTER_UNNECESSARY"


def test_persistence_review():
    cache = _cache(
        tier="Premium",
        redis_config={"rdbBackupEnabled": "true"},
    )
    sku = parse_redis_arm_sku(cache)
    draft = evaluate_redis_persistence(cache, sku, 75.0, ADVANCED_RULES["REDIS_PERSISTENCE_REVIEW"])
    assert draft is not None
    assert "RDB" in draft.detail


def test_tier_review_multi_shard():
    cache = _cache(tier="Premium", capacity=3, shards=3, redis_config={"maxmemoryPolicy": "volatile-lru"})
    sku = parse_redis_arm_sku(cache)
    draft = evaluate_redis_tier_review(cache, sku, 100.0, ADVANCED_RULES["REDIS_TIER_REVIEW"])
    assert draft is not None
    assert draft.rule_id == "REDIS_TIER_REVIEW"
    cache2 = _cache(tier="Premium", capacity=1, shards=1, redis_config={"maxmemoryPolicy": "allkeys-lru"})
    sku2 = parse_redis_arm_sku(cache2)
    draft2 = evaluate_redis_tier_review(cache2, sku2, 100.0, ADVANCED_RULES["REDIS_TIER_REVIEW"])
    assert draft2 is None


def test_analyze_redis_integration():
    engine = _FakeEngine()
    caches = [
        _cache(facts={"ops_per_sec": 0.0, "memory_pct": 2.0}),
        _cache(name="failed", facts={}),
    ]
    caches[1]["properties"]["provisioningState"] = "Failed"
    findings = analyze_redis(engine, "sub", caches, {caches[0]["id"].lower(): 50.0})
    rule_ids = {f.rule_id for f in findings}
    assert "REDIS_IDLE_DETECTION" in rule_ids
    assert "REDIS_HEALTH_EXTENDED" in rule_ids
