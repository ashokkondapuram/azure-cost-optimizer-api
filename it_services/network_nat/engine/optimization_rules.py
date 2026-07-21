"""NAT Gateway optimization decision rules — SNAT and SKU intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.network_pricing import (
    estimate_decommission_savings,
    estimate_load_balancer_hourly,
    estimate_nat_gateway_hourly,
    estimate_rightsizing_savings,
)
from app.nat_gateway_catalog import optimization_thresholds, parse_nat_gateway_arm, snat_capacity_for_gateway, sku_spec
from app.resource_utilization import (
    confidence_with_monitor,
    fact_value,
    is_low_traffic,
    make_check,
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
        "snat_exhaustion_pct": float(getattr(rule, "nat_snat_exhaustion_pct", defaults.get("snat_exhaustion_pct", 80.0))),
        "snat_low_connections": float(getattr(rule, "nat_snat_low_connection_threshold", defaults.get("snat_low_connection_threshold", 10.0))),
        "v2_upgrade_gbps": float(getattr(rule, "nat_throughput_v2_upgrade_gbps", defaults.get("throughput_v2_upgrade_gbps", 40.0))),
        "idle_bytes": float(getattr(rule, "nat_idle_byte_threshold", defaults.get("idle_byte_threshold", 1_000_000.0))),
        "min_savings": float(getattr(rule, "min_monthly_savings_usd", defaults.get("min_monthly_savings_usd", 5.0))),
    }


def evaluate_nat_idle_unassociated(
    nat: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    subnet_count = int(ctx.get("subnet_count") or 0)
    if subnet_count > 0:
        return None
    low_traffic = is_low_traffic(nat, byte_threshold=th["idle_bytes"])
    name = nat.get("name") or ""
    detail = f"NAT Gateway '{name}' has no subnet associations."
    if low_traffic is True:
        detail = f"NAT Gateway '{name}' shows no meaningful traffic in Azure Monitor."
    savings = estimate_decommission_savings(
        monthly_cost,
        hourly_usd=estimate_nat_gateway_hourly(int(ctx.get("public_ip_count") or 1)),
        min_savings=th["min_savings"],
    )
    return NetworkFindingDraft(
        rule_id="NAT_GATEWAY_IDLE_EXTENDED",
        detail=detail,
        recommendation="Delete idle NAT Gateway or attach subnets that require outbound SNAT.",
        savings=savings,
        waste_score=80,
        confidence=confidence_with_monitor(93, nat, boost=6 if low_traffic is True else 0),
        priority="P2",
        impact="Direct idle network appliance cost",
        evidence=structured_evidence(
            nat,
            determination="unassociated_nat",
            summary="NAT Gateway has no subnet associations and is pure idle spend.",
            checks=[make_check("Subnet associations", subnet_count, "≥ 1", passed=False)],
            extra={"subnet_count": subnet_count, "monthly_cost_usd": monthly_cost},
        ),
    )


def evaluate_nat_idle_low_traffic(
    nat: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    if int(ctx.get("subnet_count") or 0) == 0:
        return None
    low_traffic = is_low_traffic(nat, byte_threshold=th["idle_bytes"])
    snat = fact_value(nat, "snat_connection_count")
    low_snat = snat is not None and snat < th["snat_low_connections"]
    if low_traffic is not True or not low_snat:
        return None
    savings = estimate_decommission_savings(
        monthly_cost,
        hourly_usd=estimate_nat_gateway_hourly(int(ctx.get("public_ip_count") or 1)),
        min_savings=th["min_savings"],
    )
    name = nat.get("name") or ""
    return NetworkFindingDraft(
        rule_id="NAT_GATEWAY_IDLE_EXTENDED",
        detail=f"NAT Gateway '{name}' is associated but shows negligible traffic in Azure Monitor.",
        recommendation="Remove unused subnet associations or delete the NAT Gateway if outbound SNAT is no longer required.",
        savings=savings,
        waste_score=74,
        confidence=confidence_with_monitor(86, nat),
        priority="P2",
        impact="Reclaim idle NAT Gateway capacity",
        evidence=structured_evidence(
            nat,
            determination="associated_low_traffic",
            summary="NAT Gateway has subnet associations but negligible byte volume and SNAT connections.",
            checks=[
                make_check("Byte count", fact_value(nat, "byte_count"), "Low", passed=True),
                make_check("SNAT connections", snat, f"< {th['snat_low_connections']:.0f}", passed=True),
                make_check("Subnet associations", ctx.get("subnet_count"), "≥ 1", passed=True),
            ],
            extra={"subnet_count": ctx.get("subnet_count"), "monthly_cost_usd": monthly_cost},
        ),
    )


def evaluate_nat_snat_exhaustion(
    nat: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    snat_pct = fact_value(nat, "snat_utilization_pct")
    snat_count = fact_value(nat, "snat_connection_count")
    capacity = snat_capacity_for_gateway(nat, ctx)
    if snat_pct is None and snat_count is not None and capacity > 0:
        snat_pct = round(snat_count / capacity * 100.0, 2)
    if snat_pct is None or snat_pct < th["snat_exhaustion_pct"]:
        return None
    name = nat.get("name") or ""
    return NetworkFindingDraft(
        rule_id="NAT_GATEWAY_SNAT_EXHAUSTION",
        detail=f"NAT Gateway '{name}' SNAT utilization is {snat_pct:.0f}% — risk of connection failures.",
        recommendation="Add public IPs, use a /60 prefix, or consolidate subnets to increase SNAT port capacity.",
        savings=0.0,
        waste_score=35,
        confidence=confidence_with_monitor(92, nat),
        priority="P1",
        impact="Prevent outbound connection failures",
        evidence=structured_evidence(
            nat,
            determination="snat_exhaustion",
            summary="SNAT connection utilization exceeds safe threshold.",
            checks=[
                make_check("SNAT utilization %", snat_pct, f"≥ {th['snat_exhaustion_pct']:.0f}%", passed=True),
                make_check("SNAT capacity (ports)", capacity, "derived", passed=True),
            ],
            extra={
                "snat_connection_count": snat_count,
                "snat_capacity_ports": capacity,
                "public_ip_count": ctx.get("public_ip_count"),
                "monthly_cost_usd": monthly_cost,
            },
        ),
    )


def evaluate_nat_sku_v2_upgrade(
    nat: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    sku = (ctx.get("sku_name") or "Standard").strip()
    if sku.replace("_", "").lower() == "standardv2":
        return None
    throughput_gbps = fact_value(nat, "throughput_gbps")
    if throughput_gbps is None:
        byte_count = fact_value(nat, "byte_count")
        if byte_count is not None and byte_count > 0:
            # Rough 7d bytes → average Gbps estimate
            throughput_gbps = round((byte_count * 8) / (7 * 86400 * 1e9), 2)
    if throughput_gbps is None or throughput_gbps < th["v2_upgrade_gbps"]:
        return None
    name = nat.get("name") or ""
    return NetworkFindingDraft(
        rule_id="NAT_GATEWAY_SKU_V2_UPGRADE",
        detail=f"NAT Gateway '{name}' sustained throughput (~{throughput_gbps:.1f} Gbps) may benefit from StandardV2.",
        recommendation="Evaluate StandardV2 for 100 Gbps capacity, zone redundancy, and IPv6 support at the same hourly rate.",
        savings=0.0,
        waste_score=30,
        confidence=confidence_with_monitor(78, nat),
        priority="P2",
        impact="Throughput headroom and HA",
        evidence=structured_evidence(
            nat,
            determination="sku_v2_candidate",
            summary="NAT Gateway throughput approaches Standard SKU limits.",
            checks=[
                make_check("Estimated throughput (Gbps)", throughput_gbps, f"≥ {th['v2_upgrade_gbps']:.0f}", passed=True),
                make_check("Current SKU", sku, "StandardV2", passed=False),
            ],
            extra={"current_sku": sku, "max_standard_gbps": sku_spec(sku).get("max_throughput_gbps"), "monthly_cost_usd": monthly_cost},
        ),
    )


def evaluate_nat_subnet_consolidation(
    nat: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    ip_count = int(ctx.get("public_ip_count") or 0)
    subnet_count = int(ctx.get("subnet_count") or 0)
    if ip_count <= 1 or subnet_count <= 1:
        return None
    low_traffic = is_low_traffic(nat, byte_threshold=th["idle_bytes"])
    if low_traffic is not True:
        return None
    savings = estimate_rightsizing_savings(
        monthly_cost,
        savings_factor=0.25,
        hourly_usd=estimate_nat_gateway_hourly(ip_count),
        min_savings=th["min_savings"],
    )
    name = nat.get("name") or ""
    return NetworkFindingDraft(
        rule_id="NAT_GATEWAY_SUBNET_CONSOLIDATION",
        detail=f"NAT Gateway '{name}' has {ip_count} public IPs across {subnet_count} subnets with low traffic.",
        recommendation="Share one NAT Gateway across subnets or reduce public IP count using a prefix where possible.",
        savings=savings,
        waste_score=60,
        confidence=confidence_with_monitor(75, nat),
        priority="P2",
        impact="Reduce per-IP NAT charges",
        evidence=structured_evidence(
            nat,
            determination="subnet_consolidation",
            summary="Multiple public IPs with low utilization may be consolidatable.",
            checks=[
                make_check("Public IP count", ip_count, "> 1", passed=True),
                make_check("Subnet count", subnet_count, "> 1", passed=True),
            ],
            extra={"public_ip_count": ip_count, "subnet_count": subnet_count, "monthly_cost_usd": monthly_cost},
        ),
    )
