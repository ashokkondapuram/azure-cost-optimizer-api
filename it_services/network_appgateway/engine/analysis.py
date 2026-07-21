"""Application Gateways optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.appgateway_utils import application_gateway_listener_details, http_listener_count
from app.app_gateway_catalog import parse_app_gateway_arm
from app.cost_utils import resource_cost
from app.cost_utils import savings_from_factor
from it_services.network_appgateway.engine.optimization_rules import (
    NetworkFindingDraft,
    evaluate_app_gateway_cu_rightsize,
    evaluate_app_gateway_cu_saturation,
    evaluate_app_gateway_idle_savings,
)
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import fact_value
from app.resource_utilization import has_healthy_appgw_backends
from app.resource_utilization import is_low_request_volume
from app.resource_utilization import is_low_traffic
from app.resource_utilization import make_check
from app.resource_utilization import monitor_facts_status
from app.resource_utilization import structured_evidence


def _append_draft(
    out: list[ExtendedFinding],
    engine: Any,
    subscription_id: str,
    gateway: dict[str, Any],
    rule: Any,
    draft: NetworkFindingDraft | None,
) -> None:
    if draft is None or not rule or not rule.enabled:
        return
    out.append(engine._finding(
        rule=rule,
        subscription_id=subscription_id,
        resource=gateway,
        detail=draft.detail,
        recommendation=draft.recommendation,
        savings=draft.savings,
        waste_score=draft.waste_score,
        confidence=draft.confidence,
        priority=draft.priority,
        impact=draft.impact,
        evidence=draft.evidence,
    ))


def analyze_app_gateways(engine, subscription_id: str, app_gateways: list[dict], cost_by_resource: dict[str, float]) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    idle_rule = engine.rules.get("APP_GATEWAY_IDLE_EXTENDED")
    cu_sat_rule = engine.rules.get("APP_GATEWAY_CU_SATURATION")
    cu_down_rule = engine.rules.get("APP_GATEWAY_CU_RIGHTSIZE_DOWN")

    for gateway in app_gateways:
        props = gateway.get("properties") or {}
        ctx = parse_app_gateway_arm(gateway)
        listener_count = http_listener_count(props)
        listener_details = application_gateway_listener_details(props)
        agw_cost = resource_cost(cost_by_resource, gateway.get("id", ""))
        name = gateway.get("name") or ""

        _append_draft(out, engine, subscription_id, gateway, cu_sat_rule, evaluate_app_gateway_cu_saturation(gateway, ctx, agw_cost, cu_sat_rule))
        _append_draft(out, engine, subscription_id, gateway, cu_down_rule, evaluate_app_gateway_cu_rightsize(gateway, ctx, agw_cost, cu_down_rule))

        if not idle_rule or not idle_rule.enabled:
            continue

        if listener_count == 0:
            sku = gateway.get("sku") or {}
            savings = evaluate_app_gateway_idle_savings(gateway, ctx, agw_cost, idle_rule) or agw_cost
            out.append(engine._finding(
                rule=idle_rule,
                subscription_id=subscription_id,
                resource=gateway,
                detail=f"Application Gateway '{name}' has no HTTP listeners configured.",
                recommendation="Delete idle gateways or restore listener configuration if the gateway is still required.",
                savings=savings,
                waste_score=86,
                confidence=confidence_with_monitor(86, gateway),
                priority="P1",
                impact="High-value idle network appliance cleanup",
                evidence=structured_evidence(
                    gateway,
                    determination="idle_no_listeners",
                    summary="Application Gateway has no HTTP listeners — it cannot route traffic and is treated as idle.",
                    checks=[make_check("HTTP listeners configured", listener_count, "≥ 1", passed=False)],
                    extra={
                        "http_listener_count": listener_count,
                        "http_listeners": listener_details,
                        "sku": sku,
                        "monthly_cost_usd": agw_cost,
                        "estimated_monthly_savings_usd": savings,
                    },
                ),
            ))
            continue

        if monitor_facts_status(gateway, "throughput_bytes", "request_count") != "available":
            continue

        low_throughput = is_low_traffic(gateway, byte_threshold=500.0)
        low_requests = is_low_request_volume(gateway, threshold=100.0)
        healthy_backends = has_healthy_appgw_backends(gateway)
        if healthy_backends is True and low_throughput is not True and low_requests is not True:
            continue

        if low_throughput is True or low_requests is True:
            throughput = fact_value(gateway, "throughput_bytes")
            requests = fact_value(gateway, "request_count")
            healthy_hosts = fact_value(gateway, "healthy_host_count")
            savings = evaluate_app_gateway_idle_savings(gateway, ctx, agw_cost, idle_rule)
            if savings <= 0 and agw_cost > 0:
                savings = savings_from_factor(agw_cost, 0.4)
            out.append(engine._finding(
                rule=idle_rule,
                subscription_id=subscription_id,
                resource=gateway,
                detail=f"Application Gateway '{name}' has listeners but very low throughput in Azure Monitor.",
                recommendation="Downsize SKU, consolidate listeners, or delete if the gateway is no longer required.",
                savings=savings,
                waste_score=72,
                confidence=confidence_with_monitor(82, gateway),
                priority="P2",
                impact="Application gateway SKU and idle capacity optimization",
                evidence=structured_evidence(
                    gateway,
                    determination="low_throughput",
                    summary="Application Gateway has HTTP listeners but very low throughput in Azure Monitor.",
                    checks=[
                        make_check("Throughput (bytes)", throughput, "< 500", passed=low_throughput is True),
                        make_check("Request count", requests, "< 100", passed=low_requests is True),
                        make_check(
                            "Healthy backend hosts",
                            healthy_hosts,
                            "≥ 1 with traffic",
                            passed=healthy_backends is not True,
                        ),
                    ],
                    extra={
                        "http_listener_count": listener_count,
                        "http_listeners": listener_details,
                        "throughput_bytes": throughput,
                        "request_count": requests,
                        "healthy_host_count": healthy_hosts,
                        "monthly_cost_usd": agw_cost,
                        "estimated_monthly_savings_usd": savings,
                    },
                ),
            ))
    return out
