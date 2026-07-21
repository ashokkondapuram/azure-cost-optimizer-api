"""Analysis rules — owned by network-privateendpoint IT service."""
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


def analyze_private_endpoints(
    engine,
    subscription_id: str,
    endpoints: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    failed_rule = engine.rules.get("PRIVATE_ENDPOINT_FAILED_EXTENDED")
    orphan_rule = engine.rules.get("PRIVATE_ENDPOINT_ORPHAN_EXTENDED")
    under_rule = engine.rules.get("PRIVATE_ENDPOINT_UNDERUTILIZED")

    for endpoint in endpoints:
        ctx = parse_private_endpoint_arm(endpoint)
        monthly = resource_cost(cost_by_resource, endpoint.get("id", ""))
        name = endpoint.get("name") or ""
        connection_state = str(ctx.get("connection_state") or "").lower()

        if failed_rule and failed_rule.enabled and connection_state in {"rejected", "failed", "disconnected"}:
            from app.private_endpoint_catalog import hourly_baseline_usd
            from app.network_pricing import estimate_decommission_savings
            savings = estimate_decommission_savings(monthly, hourly_usd=hourly_baseline_usd())
            out.append(engine._finding(
                rule=failed_rule,
                subscription_id=subscription_id,
                resource=endpoint,
                detail=f"Private endpoint '{name}' connection state is {connection_state}.",
                recommendation="Fix the private link connection or delete the endpoint to stop hourly charges.",
                savings=savings,
                waste_score=72,
                confidence=88,
                priority="P1",
                impact="Stop billing on failed private endpoint connections",
                evidence=structured_evidence(
                    endpoint,
                    determination="connection_failed",
                    summary="Private endpoint connection is not approved.",
                    checks=[make_check("Connection state", connection_state, "Approved", passed=False)],
                    extra={"connection_state": connection_state, "monthly_cost_usd": monthly, "estimated_monthly_savings_usd": savings},
                ),
            ))
            continue

        _append_draft(out, engine, subscription_id, endpoint, orphan_rule, evaluate_private_endpoint_orphan(endpoint, ctx, monthly, orphan_rule))
        _append_draft(out, engine, subscription_id, endpoint, under_rule, evaluate_private_endpoint_underutilized(endpoint, ctx, monthly, under_rule))
    return out
