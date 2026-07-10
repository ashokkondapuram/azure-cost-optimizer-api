"""Public IPs optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from it_services.network_publicip.engine.optimization_rules import (
    NetworkFindingDraft,
    evaluate_public_ip_basic_sku_migration,
    evaluate_public_ip_idle_traffic,
    evaluate_public_ip_unassociated,
)
from app.cost_utils import resource_cost
from app.public_ip_catalog import parse_public_ip_arm


def _append_draft(
    out: list[ExtendedFinding],
    engine: Any,
    subscription_id: str,
    ip: dict[str, Any],
    rule: Any,
    draft: NetworkFindingDraft | None,
) -> None:
    if draft is None or not rule or not rule.enabled:
        return
    out.append(engine._finding(
        rule=rule,
        subscription_id=subscription_id,
        resource=ip,
        detail=draft.detail,
        recommendation=draft.recommendation,
        savings=draft.savings,
        waste_score=draft.waste_score,
        confidence=draft.confidence,
        priority=draft.priority,
        impact=draft.impact,
        evidence=draft.evidence,
    ))


def analyze_public_ips(
    engine,
    subscription_id: str,
    public_ips: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rules = {
        "PUBLIC_IP_IDLE_EXTENDED": engine.rules.get("PUBLIC_IP_IDLE_EXTENDED"),
        "PUBLIC_IP_BASIC_SKU_MIGRATION": engine.rules.get("PUBLIC_IP_BASIC_SKU_MIGRATION"),
    }

    for ip in public_ips:
        ctx = parse_public_ip_arm(ip)
        monthly = resource_cost(cost_by_resource, ip.get("id", ""))

        idle_rule = rules["PUBLIC_IP_IDLE_EXTENDED"]
        for evaluator in (
            evaluate_public_ip_unassociated,
            evaluate_public_ip_idle_traffic,
        ):
            _append_draft(out, engine, subscription_id, ip, idle_rule, evaluator(ip, ctx, monthly, idle_rule))

        basic_rule = rules["PUBLIC_IP_BASIC_SKU_MIGRATION"]
        _append_draft(
            out, engine, subscription_id, ip, basic_rule,
            evaluate_public_ip_basic_sku_migration(ip, ctx, monthly, basic_rule),
        )

    return out
