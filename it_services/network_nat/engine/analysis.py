"""NAT Gateways optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from it_services.network_nat.engine.optimization_rules import (
    NetworkFindingDraft,
    evaluate_nat_idle_low_traffic,
    evaluate_nat_idle_unassociated,
    evaluate_nat_sku_v2_upgrade,
    evaluate_nat_snat_exhaustion,
    evaluate_nat_subnet_consolidation,
)
from app.cost_utils import resource_cost
from app.nat_gateway_catalog import parse_nat_gateway_arm


def _append_draft(
    out: list[ExtendedFinding],
    engine: Any,
    subscription_id: str,
    nat: dict[str, Any],
    rule: Any,
    draft: NetworkFindingDraft | None,
) -> None:
    if draft is None or not rule or not rule.enabled:
        return
    out.append(engine._finding(
        rule=rule,
        subscription_id=subscription_id,
        resource=nat,
        detail=draft.detail,
        recommendation=draft.recommendation,
        savings=draft.savings,
        waste_score=draft.waste_score,
        confidence=draft.confidence,
        priority=draft.priority,
        impact=draft.impact,
        evidence=draft.evidence,
    ))


def analyze_nat_gateways(
    engine,
    subscription_id: str,
    nat_gateways: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rules = {
        "NAT_GATEWAY_IDLE_EXTENDED": engine.rules.get("NAT_GATEWAY_IDLE_EXTENDED"),
        "NAT_GATEWAY_SNAT_EXHAUSTION": engine.rules.get("NAT_GATEWAY_SNAT_EXHAUSTION"),
        "NAT_GATEWAY_SKU_V2_UPGRADE": engine.rules.get("NAT_GATEWAY_SKU_V2_UPGRADE"),
        "NAT_GATEWAY_SUBNET_CONSOLIDATION": engine.rules.get("NAT_GATEWAY_SUBNET_CONSOLIDATION"),
    }

    for nat in nat_gateways:
        ctx = parse_nat_gateway_arm(nat)
        monthly = resource_cost(cost_by_resource, nat.get("id", ""))

        idle_rule = rules["NAT_GATEWAY_IDLE_EXTENDED"]
        for evaluator in (evaluate_nat_idle_unassociated, evaluate_nat_idle_low_traffic):
            _append_draft(out, engine, subscription_id, nat, idle_rule, evaluator(nat, ctx, monthly, idle_rule))

        for rule_id, evaluator in (
            ("NAT_GATEWAY_SNAT_EXHAUSTION", evaluate_nat_snat_exhaustion),
            ("NAT_GATEWAY_SKU_V2_UPGRADE", evaluate_nat_sku_v2_upgrade),
            ("NAT_GATEWAY_SUBNET_CONSOLIDATION", evaluate_nat_subnet_consolidation),
        ):
            rule = rules[rule_id]
            _append_draft(out, engine, subscription_id, nat, rule, evaluator(nat, ctx, monthly, rule))

    return out
