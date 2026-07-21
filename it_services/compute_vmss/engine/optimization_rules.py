"""VMSS optimization decision rules — autoscale tuning and capacity metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.compute_pricing import estimate_instance_pool_savings, vmss_instance_hourly_baseline
from app.resource_utilization import (
    confidence_with_monitor,
    cpu_pct,
    fact_value,
    make_check,
    monitor_facts_status,
    structured_evidence,
)
from app.vmss_metrics_catalog import autoscale_defaults, optimization_thresholds


@dataclass(frozen=True)
class ComputeFindingDraft:
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
    scale = autoscale_defaults()
    return {
        "scale_out_pct": float(getattr(rule, "vmss_scale_out_cpu_pct", scale.get("recommended_scale_out_cpu_pct", 70.0))),
        "scale_in_pct": float(getattr(rule, "vmss_scale_in_cpu_pct", scale.get("recommended_scale_in_cpu_pct", 30.0))),
        "cpu_downsize_pct": float(getattr(rule, "cpu_downsize_pct", defaults.get("cpu_downsize_pct", 30.0))),
        "min_savings": float(getattr(rule, "min_monthly_savings_usd", defaults.get("min_monthly_savings_usd", 10.0))),
    }


def evaluate_vmss_autoscale_tuning(
    vmss: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> ComputeFindingDraft | None:
    if not ctx.get("has_autoscale"):
        return None
    th = _thresholds(rule)
    if monitor_facts_status(vmss, "avg_cpu_pct") != "available":
        return None
    cpu = cpu_pct(vmss) or fact_value(vmss, "avg_cpu_pct")
    if cpu is None:
        return None
    cpu_f = float(cpu)
    name = vmss.get("name") or ""
    capacity = int(ctx.get("capacity") or 0)

    if cpu_f < th["scale_in_pct"]:
        savings = estimate_instance_pool_savings(
            monthly_cost,
            instance_hourly_usd=vmss_instance_hourly_baseline(),
            capacity=capacity,
            savings_factor=0.25,
            min_savings=th["min_savings"],
        )
        return ComputeFindingDraft(
            rule_id="VMSS_AUTOSCALE_TUNING_EXTENDED",
            detail=(
                f"VMSS '{name}' averages {cpu_f:.1f}% CPU with autoscale enabled — "
                f"scale-in threshold may be too conservative (recommended < {th['scale_in_pct']:.0f}%)."
            ),
            recommendation=(
                f"Tune autoscale to scale in below {th['scale_in_pct']:.0f}% CPU "
                f"with a {int(autoscale_defaults().get('scale_in_cooldown_minutes', 10))}-minute cooldown to reduce over-provisioning."
            ),
            savings=savings,
            waste_score=58,
            confidence=confidence_with_monitor(80, vmss),
            priority="P2",
            impact="Autoscale tuning can reduce fixed instance overhead",
            evidence=structured_evidence(
                vmss,
                determination="autoscale_scale_in_tuning",
                summary="Scale set CPU is low while autoscale is enabled — tune scale-in rules.",
                checks=[
                    make_check("Average CPU %", cpu_f, f"< {th['scale_in_pct']:.0f}%", passed=True),
                    make_check("Instance count", capacity, "> 1", passed=capacity > 1),
                ],
                extra={"vm_size": ctx.get("vm_size"), "monthly_cost_usd": monthly_cost},
            ),
        )

    if cpu_f > th["scale_out_pct"]:
        return ComputeFindingDraft(
            rule_id="VMSS_AUTOSCALE_TUNING_EXTENDED",
            detail=(
                f"VMSS '{name}' averages {cpu_f:.1f}% CPU — autoscale may need earlier scale-out "
                f"(recommended > {th['scale_out_pct']:.0f}%)."
            ),
            recommendation=f"Review autoscale scale-out rules to trigger near {th['scale_out_pct']:.0f}% CPU to avoid saturation.",
            savings=0.0,
            waste_score=45,
            confidence=confidence_with_monitor(76, vmss),
            priority="P3",
            impact="Performance tuning — prevent CPU saturation before scale-out",
            evidence=structured_evidence(
                vmss,
                determination="autoscale_scale_out_tuning",
                summary="Scale set CPU is elevated — validate scale-out thresholds.",
                checks=[
                    make_check("Average CPU %", cpu_f, f"> {th['scale_out_pct']:.0f}%", passed=True),
                ],
                extra={"capacity": capacity, "monthly_cost_usd": monthly_cost},
            ),
        )
    return None
