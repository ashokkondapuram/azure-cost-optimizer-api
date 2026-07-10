"""Optimization rules — owned by network-vnet IT service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.network_pricing import estimate_peering_savings
from app.vnet_catalog import optimization_thresholds
from app.resource_utilization import make_check, structured_evidence


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
        "min_savings": float(getattr(rule, "min_monthly_savings_usd", defaults.get("min_monthly_savings_usd", 10.0))),
    }


def evaluate_vnet_peering_consolidation(
    vnet: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    peering_count = int(ctx.get("peering_count") or 0)
    if peering_count <= 0:
        return None
    name = vnet.get("name") or ""
    savings = estimate_peering_savings(
        peering_count,
        monthly_cost,
        savings_factor=0.15,
        min_savings=th["min_savings"],
    )
    return NetworkFindingDraft(
        rule_id="VNET_PEERING_CONSOLIDATION_EXTENDED",
        detail=(
            f"Virtual network '{name}' has {peering_count} peering(s)"
            + (f" and MTD network spend of ${monthly_cost:,.2f}." if monthly_cost > 0 else ".")
        ),
        recommendation="Review cross-region peering and data transfer paths; consolidate VNets or use hub-spoke designs.",
        savings=savings,
        waste_score=44,
        confidence=58,
        priority="P2",
        impact="Reduce peering and cross-region transfer cost",
        evidence=structured_evidence(
            vnet,
            determination="peering_consolidation",
            summary="Virtual network peerings may drive recurring transfer spend.",
            checks=[make_check("Peering count", peering_count, "≥ 1", passed=True)],
            extra={"peering_count": peering_count, "monthly_cost_usd": monthly_cost, "estimated_monthly_savings_usd": savings},
        ),
    )


def evaluate_vnet_unused_subnet(
    vnet: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    empty = int(ctx.get("empty_subnet_count") or 0)
    if empty <= 0:
        return None
    name = vnet.get("name") or ""
    return NetworkFindingDraft(
        rule_id="VNET_UNUSED_SUBNET_EXTENDED",
        detail=f"Virtual network '{name}' has {empty} subnet(s) with no attached resources.",
        recommendation="Remove unused address space or consolidate subnets to simplify routing and governance.",
        savings=0.0,
        waste_score=32,
        confidence=70,
        priority="P3",
        impact="Network hygiene — reduces address space fragmentation",
        evidence=structured_evidence(
            vnet,
            determination="unused_subnet",
            summary="Virtual network contains empty subnets.",
            checks=[make_check("Empty subnets", empty, "≥ 1", passed=True)],
            extra={"empty_subnet_count": empty, "monthly_cost_usd": monthly_cost},
        ),
    )
