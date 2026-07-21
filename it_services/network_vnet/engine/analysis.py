"""Analysis rules — owned by network-vnet IT service."""
from __future__ import annotations

from __future__ import annotations
from typing import Any
from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.cost_utils import savings_from_factor
from it_services.network_privateendpoint.engine.optimization_rules import (
    NetworkFindingDraft as PeDraft,
    evaluate_private_endpoint_orphan,
    evaluate_private_endpoint_underutilized,
)
from it_services.network_privatelinkservice.engine.optimization_rules import (
    NetworkFindingDraft as PlsDraft,
    evaluate_private_link_nat_pressure,
    evaluate_private_link_nat_rightsize,
    evaluate_private_link_unused,
)
from it_services.network_privatedns.engine.optimization_rules import (
    NetworkFindingDraft as DnsDraft,
    evaluate_private_dns_empty,
    evaluate_private_dns_unused_zone,
)
from it_services.network_vnet.engine.optimization_rules import (
    NetworkFindingDraft as VnetDraft,
    evaluate_vnet_peering_consolidation,
    evaluate_vnet_unused_subnet,
)
from app.private_dns_catalog import parse_private_dns_arm
from app.private_endpoint_catalog import parse_private_endpoint_arm
from app.private_link_service_catalog import parse_private_link_service_arm
from app.resource_utilization import make_check
from app.resource_utilization import structured_evidence
from app.vnet_catalog import parse_vnet_arm
def _append_draft(
    out: list[ExtendedFinding],
    engine: Any,
    subscription_id: str,
    resource: dict[str, Any],
    rule: Any,
    draft: PeDraft | PlsDraft | DnsDraft | VnetDraft | None,
) -> None:
    if draft is None or not rule or not rule.enabled:
        return
    out.append(engine._finding(
        rule=rule,
        subscription_id=subscription_id,
        resource=resource,
        detail=draft.detail,
        recommendation=draft.recommendation,
        savings=draft.savings,
        waste_score=draft.waste_score,
        confidence=draft.confidence,
        priority=draft.priority,
        impact=draft.impact,
        evidence=draft.evidence,
    ))


def analyze_vnets(
    engine,
    subscription_id: str,
    vnets: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    peering_rule = engine.rules.get("VNET_PEERING_CONSOLIDATION_EXTENDED")
    subnet_rule = engine.rules.get("VNET_UNUSED_SUBNET_EXTENDED")
    legacy_rule = engine.rules.get("VNET_PEERING_REVIEW_EXTENDED")

    for vnet in vnets:
        ctx = parse_vnet_arm(vnet)
        monthly = resource_cost(cost_by_resource, vnet.get("id", ""))
        _append_draft(out, engine, subscription_id, vnet, peering_rule or legacy_rule, evaluate_vnet_peering_consolidation(vnet, ctx, monthly, peering_rule or legacy_rule))
        _append_draft(out, engine, subscription_id, vnet, subnet_rule, evaluate_vnet_unused_subnet(vnet, ctx, monthly, subnet_rule))
    return out
