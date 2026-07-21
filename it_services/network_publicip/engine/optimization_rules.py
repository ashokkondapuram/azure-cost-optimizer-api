"""Public IP optimization decision rules — metrics + SKU intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.network_pricing import estimate_decommission_savings
from app.public_ip_catalog import basic_sku_retirement_date, load_public_ip_specifications, optimization_thresholds, parse_public_ip_arm
from app.resource_utilization import (
    confidence_with_monitor,
    fact_value,
    is_idle_public_ip_traffic,
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
        "idle_byte_threshold": float(getattr(rule, "public_ip_idle_byte_threshold", defaults.get("idle_byte_threshold", 100.0))),
        "idle_packet_threshold": float(getattr(rule, "public_ip_idle_packet_threshold", defaults.get("idle_packet_threshold", 100.0))),
        "min_savings": float(getattr(rule, "min_monthly_savings_usd", defaults.get("min_monthly_savings_usd", 2.0))),
    }


def evaluate_public_ip_unassociated(
    ip: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    if ctx.get("allocation") != "Static" or ctx.get("is_associated"):
        return None
    savings = estimate_decommission_savings(
        monthly_cost,
        hourly_usd=float(load_public_ip_specifications().get("pricing", {}).get("hourly_usd_baseline", 0.004)),
        min_savings=th["min_savings"],
    )
    name = ip.get("name") or ""
    return NetworkFindingDraft(
        rule_id="PUBLIC_IP_IDLE_EXTENDED",
        detail=f"Public IP '{name}' is static and not associated to any live resource.",
        recommendation="Delete idle static public IPs after confirming no DNS or failover dependency exists.",
        savings=savings,
        waste_score=80,
        confidence=95,
        priority="P2",
        impact="Low-risk direct network savings",
        evidence=structured_evidence(
            ip,
            determination="ip_unassociated",
            summary="Static public IP has no association to a NIC, load balancer, or NAT gateway.",
            checks=[
                make_check("Allocation method", ctx.get("allocation"), "Static", passed=True),
                make_check("Resource association", ctx.get("is_associated"), "Associated", passed=False),
            ],
            extra={"allocation": ctx.get("allocation"), "monthly_cost_usd": monthly_cost},
        ),
    )


def evaluate_public_ip_idle_traffic(
    ip: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    if ctx.get("allocation") != "Static" or not ctx.get("is_associated"):
        return None
    if monitor_facts_status(ip, "byte_count", "packet_count") != "available":
        return None
    traffic_idle = is_idle_public_ip_traffic(
        ip,
        byte_threshold=th["idle_byte_threshold"],
        packet_threshold=th["idle_packet_threshold"],
    )
    if traffic_idle is not True:
        return None
    savings = estimate_decommission_savings(
        monthly_cost,
        hourly_usd=float(load_public_ip_specifications().get("pricing", {}).get("hourly_usd_baseline", 0.004)),
        savings_factor=0.5 if monthly_cost > 0 else 1.0,
        min_savings=th["min_savings"],
    )
    name = ip.get("name") or ""
    return NetworkFindingDraft(
        rule_id="PUBLIC_IP_IDLE_EXTENDED",
        detail=f"Public IP '{name}' is associated but shows negligible traffic in Azure Monitor.",
        recommendation="Review whether the IP is still required; detach and delete if the workload no longer needs a public endpoint.",
        savings=savings,
        waste_score=72,
        confidence=confidence_with_monitor(88, ip),
        priority="P2",
        impact="Reclaim unused public IP capacity",
        evidence=structured_evidence(
            ip,
            determination="associated_low_traffic",
            summary="Associated static public IP shows negligible byte and packet volume over the monitor window.",
            checks=[
                make_check("Byte count", fact_value(ip, "byte_count"), f"< {th['idle_byte_threshold']:.0f}", passed=True),
                make_check("Packet count", fact_value(ip, "packet_count"), f"< {th['idle_packet_threshold']:.0f}", passed=True),
            ],
            extra={"allocation": ctx.get("allocation"), "monthly_cost_usd": monthly_cost},
        ),
    )


def evaluate_public_ip_basic_sku_migration(
    ip: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    sku = (ctx.get("sku_name") or "").strip()
    if sku.lower() != "basic" and not ctx.get("sku_retiring"):
        return None
    name = ip.get("name") or ""
    target = ctx.get("migrate_to_sku") or "Standard"
    return NetworkFindingDraft(
        rule_id="PUBLIC_IP_BASIC_SKU_MIGRATION",
        detail=f"Public IP '{name}' uses Basic SKU, which retires on {basic_sku_retirement_date()}.",
        recommendation=f"Upgrade to {target} SKU before retirement to avoid service disruption. Hourly cost is comparable.",
        savings=0.0,
        waste_score=55,
        confidence=98,
        priority="P2",
        impact="Continuity before Basic SKU retirement",
        evidence=structured_evidence(
            ip,
            determination="basic_sku_migration",
            summary=f"Basic public IP must migrate to {target} before Azure retirement deadline.",
            checks=[
                make_check("SKU", sku, "Basic", passed=True),
                make_check("Retirement date", basic_sku_retirement_date(), "2025-09-30", passed=True),
            ],
            extra={"current_sku": sku, "target_sku": target, "monthly_cost_usd": monthly_cost},
        ),
    )
