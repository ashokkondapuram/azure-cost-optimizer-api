"""Optimization rules — owned by network-privatelinkservice IT service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.network_pricing import estimate_decommission_savings, estimate_rightsizing_savings
from app.private_link_service_catalog import hourly_baseline_usd, optimization_thresholds
from app.resource_utilization import (
    confidence_with_monitor,
    fact_value,
    make_check,
    monitor_facts_status,
    structured_evidence,
)


@dataclass(frozen=True)
class NetworkFindingDraft:
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
        "nat_pressure_pct": float(getattr(rule, "pls_nat_port_pressure_pct", defaults.get("nat_port_pressure_pct", 80.0))),
        "nat_low_pct": float(getattr(rule, "pls_nat_port_low_pct", defaults.get("nat_port_low_pct", 30.0))),
        "min_savings": float(getattr(rule, "min_monthly_savings_usd", defaults.get("min_monthly_savings_usd", 5.0))),
    }


def evaluate_private_link_unused(
    service: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    if int(ctx.get("connection_count") or 0) > 0:
        return None
    name = service.get("name") or ""
    savings = estimate_decommission_savings(
        monthly_cost,
        hourly_usd=hourly_baseline_usd(),
        min_savings=th["min_savings"],
    )
    return NetworkFindingDraft(
        rule_id="PRIVATE_LINK_UNUSED_EXTENDED",
        detail=f"Private link service '{name}' has no private endpoint connections.",
        recommendation="Delete unused private link services or onboard consumers via approved private endpoints.",
        savings=savings,
        waste_score=54,
        confidence=78,
        priority="P2",
        impact="Remove idle private link service hourly charges",
        evidence=structured_evidence(
            service,
            determination="unused_private_link",
            summary="Private link service has zero endpoint connections.",
            checks=[make_check("Endpoint connections", ctx.get("connection_count"), "≥ 1", passed=False)],
            extra={"monthly_cost_usd": monthly_cost, "estimated_monthly_savings_usd": savings},
        ),
    )


def evaluate_private_link_nat_pressure(
    service: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    nat_pct = fact_value(service, "pls_nat_port_usage_pct")
    if nat_pct is None or float(nat_pct) < th["nat_pressure_pct"]:
        return None
    name = service.get("name") or ""
    return NetworkFindingDraft(
        rule_id="PRIVATE_LINK_NAT_PORT_PRESSURE",
        detail=f"Private link service '{name}' NAT port usage is {float(nat_pct):.0f}% — connection risk.",
        recommendation="Scale out NAT ports or split consumers across additional private link service instances.",
        savings=0.0,
        waste_score=48,
        confidence=confidence_with_monitor(86, service),
        priority="P1",
        impact="Prevent private link NAT port exhaustion",
        evidence=structured_evidence(
            service,
            determination="nat_port_pressure",
            summary="Private link NAT port utilization exceeds safe threshold.",
            checks=[make_check("NAT port usage %", nat_pct, f">= {th['nat_pressure_pct']:.0f}%", passed=True)],
            extra={"monthly_cost_usd": monthly_cost},
        ),
    )


def evaluate_private_link_nat_rightsize(
    service: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    if monitor_facts_status(service, "pls_nat_port_usage_pct") != "available":
        return None
    nat_pct = fact_value(service, "pls_nat_port_usage_pct")
    if nat_pct is None or float(nat_pct) >= th["nat_low_pct"]:
        return None
    name = service.get("name") or ""
    savings = estimate_rightsizing_savings(
        monthly_cost,
        savings_factor=0.25,
        hourly_usd=hourly_baseline_usd(),
        min_savings=th["min_savings"],
    )
    return NetworkFindingDraft(
        rule_id="PRIVATE_LINK_NAT_RIGHTSIZE",
        detail=f"Private link service '{name}' NAT port usage is only {float(nat_pct):.0f}% — over-provisioned.",
        recommendation="Consolidate private endpoint consumers or reduce NAT port allocation after validating peak load.",
        savings=savings,
        waste_score=50,
        confidence=confidence_with_monitor(74, service),
        priority="P2",
        impact="Optimize private link NAT footprint",
        evidence=structured_evidence(
            service,
            determination="nat_rightsize",
            summary="Low NAT port utilization suggests consolidation opportunity.",
            checks=[make_check("NAT port usage %", nat_pct, f"< {th['nat_low_pct']:.0f}%", passed=True)],
            extra={"monthly_cost_usd": monthly_cost, "estimated_monthly_savings_usd": savings},
        ),
    )
