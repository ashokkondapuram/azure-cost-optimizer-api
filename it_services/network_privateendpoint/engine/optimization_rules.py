"""Optimization rules — owned by network-privateendpoint IT service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.network_pricing import estimate_decommission_savings, estimate_rightsizing_savings
from app.private_endpoint_catalog import hourly_baseline_usd, optimization_thresholds, parse_private_endpoint_arm
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
        "underutilized_bytes": float(
            getattr(rule, "pe_underutilized_bytes_monthly", defaults.get("underutilized_bytes_monthly", 0))
        ),
        "min_savings": float(getattr(rule, "min_monthly_savings_usd", defaults.get("min_monthly_savings_usd", 5.0))),
    }


def _pe_bytes_total(endpoint: dict[str, Any]) -> float | None:
    total = fact_value(endpoint, "pe_bytes_total")
    if total is not None:
        return float(total)
    inbound = fact_value(endpoint, "pe_bytes_in")
    outbound = fact_value(endpoint, "pe_bytes_out")
    if inbound is None and outbound is None:
        return None
    return float(inbound or 0.0) + float(outbound or 0.0)


def orphan_savings(monthly_cost: float, min_savings: float) -> float:
    return estimate_decommission_savings(
        monthly_cost,
        hourly_usd=hourly_baseline_usd(),
        min_savings=min_savings,
    )


def evaluate_private_endpoint_underutilized(
    endpoint: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    if ctx.get("connection_state") not in {"approved", "connected", "succeeded"}:
        return None
    if monitor_facts_status(endpoint, "pe_bytes_in", "pe_bytes_out", "pe_bytes_total") not in {"available", "partial"}:
        return None
    total_bytes = _pe_bytes_total(endpoint)
    if total_bytes is None or total_bytes >= th["underutilized_bytes"]:
        return None
    name = endpoint.get("name") or ""
    savings = estimate_rightsizing_savings(
        monthly_cost,
        savings_factor=0.90,
        hourly_usd=hourly_baseline_usd(),
        min_savings=th["min_savings"],
    )
    gb = total_bytes / (1024**3)
    return NetworkFindingDraft(
        rule_id="PRIVATE_ENDPOINT_UNDERUTILIZED",
        detail=(
            f"Private endpoint '{name}' transferred only {gb:.1f} GB over the evaluation window — "
            "likely underutilized."
        ),
        recommendation="Delete unused private endpoints or consolidate duplicate connections to the same target service.",
        savings=savings,
        waste_score=56,
        confidence=confidence_with_monitor(78, endpoint),
        priority="P2",
        impact="Remove hourly private endpoint charges for idle connections",
        evidence=structured_evidence(
            endpoint,
            determination="underutilized_endpoint",
            summary="Private endpoint byte volume is below utilization threshold.",
            checks=[make_check("Total bytes", total_bytes, f"< {th['underutilized_bytes']:.0f}", passed=True)],
            extra={"monthly_cost_usd": monthly_cost, "estimated_monthly_savings_usd": savings},
        ),
    )


def evaluate_private_endpoint_orphan(
    endpoint: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    if ctx.get("target_resource_id"):
        return None
    name = endpoint.get("name") or ""
    savings = orphan_savings(monthly_cost, th["min_savings"])
    return NetworkFindingDraft(
        rule_id="PRIVATE_ENDPOINT_ORPHAN_EXTENDED",
        detail=f"Private endpoint '{name}' has no approved target connection.",
        recommendation="Delete orphaned private endpoints after validating DNS zone group dependencies.",
        savings=savings,
        waste_score=58,
        confidence=80,
        priority="P2",
        impact="Remove unused private endpoint hourly charges",
        evidence=structured_evidence(
            endpoint,
            determination="orphaned_endpoint",
            summary="Private endpoint lacks an approved private link target.",
            checks=[make_check("Target resource", ctx.get("target_resource_id"), "Present", passed=False)],
            extra={"monthly_cost_usd": monthly_cost, "estimated_monthly_savings_usd": savings},
        ),
    )
