"""Load Balancers optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from it_services.network_loadbalancer.engine.optimization_rules import (
    NetworkFindingDraft,
    evaluate_lb_basic_sku_migration,
    evaluate_lb_idle_no_backends,
    evaluate_lb_low_traffic,
    evaluate_lb_snat_pressure,
    evaluate_lb_throughput_rightsize,
)
from app.cost_utils import resource_cost
from app.load_balancer_catalog import parse_load_balancer_arm


def _append_draft(
    out: list[ExtendedFinding],
    engine: Any,
    subscription_id: str,
    lb: dict[str, Any],
    rule: Any,
    draft: NetworkFindingDraft | None,
) -> None:
    if draft is None or not rule or not rule.enabled:
        return
    out.append(engine._finding(
        rule=rule,
        subscription_id=subscription_id,
        resource=lb,
        detail=draft.detail,
        recommendation=draft.recommendation,
        savings=draft.savings,
        waste_score=draft.waste_score,
        confidence=draft.confidence,
        priority=draft.priority,
        impact=draft.impact,
        evidence=draft.evidence,
    ))


def analyze_load_balancers(
    engine,
    subscription_id: str,
    load_balancers: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rules = {
        "LOAD_BALANCER_IDLE_EXTENDED": engine.rules.get("LOAD_BALANCER_IDLE_EXTENDED"),
        "LOAD_BALANCER_BACKEND_CONSOLIDATION": engine.rules.get("LOAD_BALANCER_BACKEND_CONSOLIDATION"),
        "LOAD_BALANCER_SNAT_PRESSURE": engine.rules.get("LOAD_BALANCER_SNAT_PRESSURE"),
        "LOAD_BALANCER_THROUGHPUT_RIGHTSIZE": engine.rules.get("LOAD_BALANCER_THROUGHPUT_RIGHTSIZE"),
        "LOAD_BALANCER_BASIC_SKU_MIGRATION": engine.rules.get("LOAD_BALANCER_BASIC_SKU_MIGRATION"),
    }

    for lb in load_balancers:
        ctx = parse_load_balancer_arm(lb)
        monthly = resource_cost(cost_by_resource, lb.get("id", ""))

        idle_rule = rules["LOAD_BALANCER_IDLE_EXTENDED"]
        _append_draft(
            out, engine, subscription_id, lb, idle_rule,
            evaluate_lb_idle_no_backends(lb, ctx, monthly, idle_rule),
        )

        for rule_id, evaluator in (
            ("LOAD_BALANCER_BACKEND_CONSOLIDATION", evaluate_lb_low_traffic),
            ("LOAD_BALANCER_SNAT_PRESSURE", evaluate_lb_snat_pressure),
            ("LOAD_BALANCER_THROUGHPUT_RIGHTSIZE", evaluate_lb_throughput_rightsize),
            ("LOAD_BALANCER_BASIC_SKU_MIGRATION", evaluate_lb_basic_sku_migration),
        ):
            rule = rules[rule_id]
            _append_draft(out, engine, subscription_id, lb, rule, evaluator(lb, ctx, monthly, rule))

    return out
