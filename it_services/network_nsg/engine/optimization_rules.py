"""NSG optimization decision rules — flow log cost attribution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.network_pricing import estimate_flow_log_savings
from app.nsg_catalog import flow_log_cost_per_gb, optimization_thresholds, parse_nsg_arm
from app.resource_utilization import fact_value, make_check, structured_evidence


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
        "min_flow_gb": float(getattr(rule, "nsg_flow_log_min_gb", defaults.get("min_flow_log_gb_month", 1.0))),
        "min_savings": float(getattr(rule, "min_monthly_savings_usd", defaults.get("min_monthly_savings_usd", 5.0))),
    }


def evaluate_nsg_orphaned(
    nsg: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    if ctx.get("subnet_count") or ctx.get("nic_count"):
        return None
    name = nsg.get("name") or ""
    return NetworkFindingDraft(
        rule_id="NSG_ORPHANED_EXTENDED",
        detail=f"NSG '{name}' is not associated with any subnet or network interface.",
        recommendation="Delete unused NSGs to reduce governance clutter and misconfiguration risk.",
        savings=monthly_cost if monthly_cost > 0 else 0.0,
        waste_score=28,
        confidence=92,
        priority="P3",
        impact="Inventory hygiene and security posture",
        evidence=structured_evidence(
            nsg,
            determination="orphaned_nsg",
            summary="NSG has no subnet or NIC associations.",
            checks=[
                make_check("Subnet associations", ctx.get("subnet_count"), "0", passed=True),
                make_check("NIC associations", ctx.get("nic_count"), "0", passed=True),
            ],
            extra={"monthly_cost_usd": monthly_cost},
        ),
    )


def evaluate_nsg_flow_log_cost(
    nsg: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    flow_bytes = fact_value(nsg, "flow_log_bytes")
    flow_gb = None
    if flow_bytes is not None:
        flow_gb = float(flow_bytes) / (1024**3)
    elif monthly_cost > 0:
        flow_gb = monthly_cost / flow_log_cost_per_gb()
    if flow_gb is None or flow_gb < th["min_flow_gb"]:
        if not ctx.get("flow_log_enabled") and monthly_cost <= 0:
            return None
    if flow_gb is None:
        flow_gb = th["min_flow_gb"]
    savings = estimate_flow_log_savings(
        gb_per_month=flow_gb,
        cost_per_gb=flow_log_cost_per_gb(),
        min_savings=th["min_savings"],
    )
    if savings <= 0 and monthly_cost <= 0:
        return None
    if monthly_cost > savings:
        savings = round(monthly_cost * 0.8, 2)
    name = nsg.get("name") or ""
    return NetworkFindingDraft(
        rule_id="NSG_FLOW_LOG_COST",
        detail=f"NSG '{name}' flow log ingestion may cost approximately ${savings:,.2f}/month with low traffic value.",
        recommendation="Disable NSG flow logs for idle NSGs or migrate to VNet flow logs with shorter retention.",
        savings=savings,
        waste_score=46,
        confidence=65,
        priority="P2",
        impact="Reduce Network Watcher flow log ingestion and storage cost",
        evidence=structured_evidence(
            nsg,
            determination="flow_log_cost",
            summary="Flow log volume or attributed cost exceeds optimization threshold.",
            checks=[make_check("Flow log GB/month", round(flow_gb, 2), f"≥ {th['min_flow_gb']}", passed=True)],
            extra={"monthly_cost_usd": monthly_cost, "estimated_monthly_savings_usd": savings},
        ),
    )
