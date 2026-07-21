"""Cosmos DB optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from it_services.database_cosmosdb.engine.optimization_rules import (
    CosmosFindingDraft,
    evaluate_cosmos_api_cost_variance,
    evaluate_cosmos_autoscale_extended,
    evaluate_cosmos_consistency_overprovisioned,
    evaluate_cosmos_failover_unnecessary,
    evaluate_cosmos_free_tier_suboptimal,
    evaluate_cosmos_hot_container,
    evaluate_cosmos_indexing_overprovisioned,
    evaluate_cosmos_large_items,
    evaluate_cosmos_multi_write_unnecessary,
    evaluate_cosmos_provisioned_extended,
    evaluate_cosmos_reserved_capacity,
    evaluate_cosmos_ru_rightsizing_over,
    evaluate_cosmos_ru_rightsizing_under,
    evaluate_cosmos_serverless,
    evaluate_cosmos_throttling,
)
from app.cost_utils import resource_cost
from app.cosmosdb_catalog import parse_cosmos_arm_account


def _append_draft(
    out: list[ExtendedFinding],
    engine: Any,
    subscription_id: str,
    account: dict[str, Any],
    rule: Any,
    draft: CosmosFindingDraft | None,
) -> None:
    if draft is None or not rule or not rule.enabled:
        return
    out.append(engine._finding(
        rule=rule,
        subscription_id=subscription_id,
        resource=account,
        detail=draft.detail,
        recommendation=draft.recommendation,
        savings=draft.savings,
        waste_score=draft.waste_score,
        confidence=draft.confidence,
        priority=draft.priority,
        impact=draft.impact,
        evidence=draft.evidence,
    ))


def analyze_cosmos(
    engine,
    subscription_id: str,
    cosmosdb: list[dict],
    cost_by_resource: dict[str, float] | None = None,
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule_ids = (
        "COSMOS_PROVISIONED_EXTENDED",
        "COSMOS_AUTOSCALE_EXTENDED",
        "COSMOS_SERVERLESS",
        "COSMOS_RU_RIGHT_SIZING_UNDER",
        "COSMOS_RU_RIGHT_SIZING_OVER",
        "COSMOS_THROTTLING_DETECTED",
        "COSMOS_HOT_CONTAINER_DETECTED",
        "COSMOS_API_COST_VARIANCE",
        "COSMOS_CONSISTENCY_OVERPROVISIONED",
        "COSMOS_LARGE_ITEMS_DETECTED",
        "COSMOS_INDEXING_OVERPROVISIONED",
        "COSMOS_MULTI_WRITE_UNNECESSARY",
        "COSMOS_FAILOVER_UNNECESSARY",
        "COSMOS_FREE_TIER_SUBOPTIMAL",
        "COSMOS_RESERVED_CAPACITY_ELIGIBLE",
    )
    rules = {rid: engine.rules.get(rid) for rid in rule_ids}
    costs = cost_by_resource or {}

    evaluators = (
        (rules["COSMOS_PROVISIONED_EXTENDED"], evaluate_cosmos_provisioned_extended),
        (rules["COSMOS_AUTOSCALE_EXTENDED"], evaluate_cosmos_autoscale_extended),
        (rules["COSMOS_SERVERLESS"], evaluate_cosmos_serverless),
        (rules["COSMOS_RU_RIGHT_SIZING_UNDER"], evaluate_cosmos_ru_rightsizing_under),
        (rules["COSMOS_RU_RIGHT_SIZING_OVER"], evaluate_cosmos_ru_rightsizing_over),
        (rules["COSMOS_THROTTLING_DETECTED"], evaluate_cosmos_throttling),
        (rules["COSMOS_HOT_CONTAINER_DETECTED"], evaluate_cosmos_hot_container),
        (rules["COSMOS_API_COST_VARIANCE"], evaluate_cosmos_api_cost_variance),
        (rules["COSMOS_CONSISTENCY_OVERPROVISIONED"], evaluate_cosmos_consistency_overprovisioned),
        (rules["COSMOS_LARGE_ITEMS_DETECTED"], evaluate_cosmos_large_items),
        (rules["COSMOS_INDEXING_OVERPROVISIONED"], evaluate_cosmos_indexing_overprovisioned),
        (rules["COSMOS_MULTI_WRITE_UNNECESSARY"], evaluate_cosmos_multi_write_unnecessary),
        (rules["COSMOS_FAILOVER_UNNECESSARY"], evaluate_cosmos_failover_unnecessary),
        (rules["COSMOS_FREE_TIER_SUBOPTIMAL"], evaluate_cosmos_free_tier_suboptimal),
        (rules["COSMOS_RESERVED_CAPACITY_ELIGIBLE"], evaluate_cosmos_reserved_capacity),
    )

    for account in cosmosdb:
        ctx = parse_cosmos_arm_account(account)
        monthly = resource_cost(costs, account.get("id", ""))
        for rule, evaluator in evaluators:
            _append_draft(out, engine, subscription_id, account, rule, evaluator(account, ctx, monthly, rule))

    return out
