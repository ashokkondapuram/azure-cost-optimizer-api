"""Redis Cache optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from it_services.database_redis.engine.optimization_rules import (
    RedisFindingDraft,
    evaluate_redis_cluster_unnecessary,
    evaluate_redis_hit_ratio,
    evaluate_redis_idle,
    evaluate_redis_low_utilization,
    evaluate_redis_memory_pressure,
    evaluate_redis_persistence,
    evaluate_redis_rightsizing,
    evaluate_redis_tier_review,
)
from app.cost_utils import resource_cost
from app.redis_sku_catalog import parse_redis_arm_sku


def _append_draft(
    out: list[ExtendedFinding],
    engine: Any,
    subscription_id: str,
    cache: dict[str, Any],
    rule: Any,
    draft: RedisFindingDraft | None,
) -> None:
    if draft is None or not rule or not rule.enabled:
        return
    out.append(engine._finding(
        rule=rule,
        subscription_id=subscription_id,
        resource=cache,
        detail=draft.detail,
        recommendation=draft.recommendation,
        savings=draft.savings,
        waste_score=draft.waste_score,
        confidence=draft.confidence,
        priority=draft.priority,
        impact=draft.impact,
        evidence=draft.evidence,
    ))


def analyze_redis(
    engine,
    subscription_id: str,
    caches: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rules = {
        "REDIS_HEALTH_EXTENDED": engine.rules.get("REDIS_HEALTH_EXTENDED"),
        "REDIS_IDLE_DETECTION": engine.rules.get("REDIS_IDLE_DETECTION"),
        "REDIS_MEMORY_PRESSURE": engine.rules.get("REDIS_MEMORY_PRESSURE"),
        "REDIS_LOW_UTILIZATION": engine.rules.get("REDIS_LOW_UTILIZATION"),
        "REDIS_HIT_RATIO_POOR": engine.rules.get("REDIS_HIT_RATIO_POOR"),
        "REDIS_CLUSTER_UNNECESSARY": engine.rules.get("REDIS_CLUSTER_UNNECESSARY"),
        "REDIS_PERSISTENCE_REVIEW": engine.rules.get("REDIS_PERSISTENCE_REVIEW"),
        "REDIS_TIER_REVIEW": engine.rules.get("REDIS_TIER_REVIEW"),
        "REDIS_RIGHTSIZE_EXTENDED": engine.rules.get("REDIS_RIGHTSIZE_EXTENDED"),
    }

    for cache in caches:
        props = cache.get("properties") or {}
        state = (props.get("provisioningState") or "").lower()
        sku_ctx = parse_redis_arm_sku(cache)
        monthly = resource_cost(cost_by_resource, cache.get("id", ""))
        name = cache.get("name") or ""

        health_rule = rules["REDIS_HEALTH_EXTENDED"]
        if health_rule and health_rule.enabled and state == "failed":
            out.append(engine._finding(
                rule=health_rule,
                subscription_id=subscription_id,
                resource=cache,
                detail=f"Redis cache '{name}' is in Failed provisioning state.",
                recommendation="Delete and recreate the cache, or escalate to Azure support.",
                savings=0,
                waste_score=92,
                confidence=97,
                priority="P1",
                impact="Availability incident and wasted spend on broken resource",
                evidence={"provisioningState": state, **sku_ctx},
            ))
            continue

        evaluators = (
            (rules["REDIS_IDLE_DETECTION"], evaluate_redis_idle),
            (rules["REDIS_MEMORY_PRESSURE"], evaluate_redis_memory_pressure),
            (rules["REDIS_LOW_UTILIZATION"], evaluate_redis_low_utilization),
            (rules["REDIS_HIT_RATIO_POOR"], evaluate_redis_hit_ratio),
            (rules["REDIS_CLUSTER_UNNECESSARY"], evaluate_redis_cluster_unnecessary),
            (rules["REDIS_PERSISTENCE_REVIEW"], evaluate_redis_persistence),
            (rules["REDIS_TIER_REVIEW"], evaluate_redis_tier_review),
            (rules["REDIS_RIGHTSIZE_EXTENDED"], evaluate_redis_rightsizing),
        )
        for rule, evaluator in evaluators:
            _append_draft(out, engine, subscription_id, cache, rule, evaluator(cache, sku_ctx, monthly, rule))

    return out
