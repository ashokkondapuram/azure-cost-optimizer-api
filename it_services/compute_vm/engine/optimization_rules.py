"""VM optimization decision rules — metrics + catalog thresholds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.resource_utilization import (
    confidence_with_monitor,
    fact_value,
    make_check,
    monitor_facts_status,
    structured_evidence,
)
from app.compute_pricing import estimate_egress_savings
from app.vm_metrics_catalog import load_vm_specifications, optimization_thresholds


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
    return {
        "cpu_downsize_pct": float(getattr(rule, "cpu_downsize_pct", defaults.get("cpu_downsize_pct", 20.0))),
        "cpu_upsize_pct": float(getattr(rule, "cpu_upsize_pct", defaults.get("cpu_upsize_pct", 80.0))),
        "memory_pressure_pct": float(
            getattr(rule, "memory_pressure_pct", 100.0 - defaults.get("memory_free_pct_min", 10.0))
        ),
        "network_egress_bytes": float(
            getattr(rule, "network_egress_bytes_monthly", defaults.get("network_egress_bytes_monthly", 0))
        ),
        "min_savings": float(getattr(rule, "min_monthly_savings_usd", defaults.get("min_monthly_savings_usd", 5.0))),
    }


def evaluate_vm_memory_pressure(
    vm: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> ComputeFindingDraft | None:
    th = _thresholds(rule)
    if monitor_facts_status(vm, "max_memory_pct", "avg_memory_pct") not in {"available", "partial"}:
        return None
    max_mem = fact_value(vm, "max_memory_pct")
    avg_mem = fact_value(vm, "avg_memory_pct")
    mem_pct = max_mem if max_mem is not None else avg_mem
    if mem_pct is None or float(mem_pct) < th["memory_pressure_pct"]:
        return None
    name = vm.get("name") or ""
    return ComputeFindingDraft(
        rule_id="VM_MEMORY_PRESSURE_EXTENDED",
        detail=(
            f"VM '{name}' shows sustained memory pressure "
            f"({float(mem_pct):.1f}% peak utilization, threshold {th['memory_pressure_pct']:.0f}%)."
        ),
        recommendation="Review memory requirements before downsizing — consider upsizing SKU or optimizing application memory usage.",
        savings=0.0,
        waste_score=62,
        confidence=confidence_with_monitor(84, vm),
        priority="P1",
        impact="Prevent performance degradation from memory-constrained workloads",
        evidence=structured_evidence(
            vm,
            determination="memory_pressure",
            summary="VM memory utilization exceeds safe downsize threshold.",
            checks=[
                make_check("Peak memory %", mem_pct, f">= {th['memory_pressure_pct']:.0f}%", passed=True),
            ],
            extra={"vm_size": ctx.get("vm_size"), "monthly_cost_usd": monthly_cost},
        ),
    )


def evaluate_vm_egress_high(
    vm: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> ComputeFindingDraft | None:
    th = _thresholds(rule)
    if th["network_egress_bytes"] <= 0:
        return None
    if monitor_facts_status(vm, "network_out_bytes") != "available":
        return None
    egress = fact_value(vm, "network_out_bytes")
    if egress is None or float(egress) < th["network_egress_bytes"]:
        return None
    name = vm.get("name") or ""
    egress_tb = float(egress) / (1024**4)
    pricing = load_vm_specifications().get("pricing") or {}
    savings = estimate_egress_savings(
        float(egress),
        monthly_cost,
        egress_factor=0.15,
        cost_per_gb_usd=float(pricing.get("egress_cost_per_gb_usd") or 0.087),
        min_savings=th["min_savings"],
    )
    return ComputeFindingDraft(
        rule_id="VM_EGRESS_HIGH_EXTENDED",
        detail=(
            f"VM '{name}' generated approximately {egress_tb:.1f} TB of network egress "
            f"over the evaluation window."
        ),
        recommendation="Review egress patterns — use Azure CDN, private endpoints, or regional peering to reduce bandwidth charges.",
        savings=savings,
        waste_score=55,
        confidence=confidence_with_monitor(78, vm),
        priority="P2",
        impact="High egress traffic increases bandwidth cost",
        evidence=structured_evidence(
            vm,
            determination="high_egress",
            summary="Network egress exceeds documented cost optimization threshold.",
            checks=[
                make_check("Network out (bytes)", egress, f">= {th['network_egress_bytes']:.0f}", passed=True),
            ],
            extra={"egress_tb": round(egress_tb, 2), "monthly_cost_usd": monthly_cost},
        ),
    )
