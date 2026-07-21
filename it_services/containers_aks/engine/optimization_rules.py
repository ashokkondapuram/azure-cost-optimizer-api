"""AKS optimization decision rules — node memory pressure and pod density."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.aks_metrics_catalog import optimization_thresholds
from app.compute_pricing import aks_node_hourly_baseline, estimate_instance_pool_savings
from app.resource_utilization import (
    confidence_with_monitor,
    cpu_pct,
    fact_value,
    make_check,
    memory_pct,
    monitor_facts_status,
    structured_evidence,
)


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
        "node_memory_pressure_pct": float(
            getattr(rule, "node_memory_pressure_pct", defaults.get("node_memory_pressure_pct", 85.0))
        ),
        "node_cpu_downsize_pct": float(getattr(rule, "node_cpu_downsize_pct", defaults.get("node_cpu_downsize_pct", 20.0))),
        "pod_density_low": float(getattr(rule, "pod_density_low_threshold", defaults.get("pod_density_low_threshold", 3.0))),
        "min_savings": float(getattr(rule, "min_monthly_savings_usd", defaults.get("min_monthly_savings_usd", 15.0))),
    }


def evaluate_aks_node_memory_pressure(
    cluster: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> ComputeFindingDraft | None:
    th = _thresholds(rule)
    if monitor_facts_status(cluster, "node_mem_pct", "max_memory_pct") not in {"available", "partial"}:
        return None
    mem = memory_pct(cluster) or fact_value(cluster, "node_mem_pct") or fact_value(cluster, "max_memory_pct")
    if mem is None or float(mem) < th["node_memory_pressure_pct"]:
        return None
    name = cluster.get("name") or ""
    return ComputeFindingDraft(
        rule_id="AKS_NODE_MEMORY_PRESSURE_EXTENDED",
        detail=(
            f"AKS cluster '{name}' shows node memory utilization at {float(mem):.1f}% "
            f"(threshold {th['node_memory_pressure_pct']:.0f}%)."
        ),
        recommendation="Scale out node pool, reduce pod memory limits, or upsize node SKU before cost optimization.",
        savings=0.0,
        waste_score=66,
        confidence=confidence_with_monitor(82, cluster),
        priority="P1",
        impact="Memory pressure risks pod eviction and service disruption",
        evidence=structured_evidence(
            cluster,
            determination="node_memory_pressure",
            summary="Cluster node memory exceeds safe optimization threshold.",
            checks=[
                make_check("Node memory %", mem, f">= {th['node_memory_pressure_pct']:.0f}%", passed=True),
            ],
            extra={"monthly_cost_usd": monthly_cost},
        ),
    )


def evaluate_aks_pod_density(
    cluster: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> ComputeFindingDraft | None:
    th = _thresholds(rule)
    if monitor_facts_status(cluster, "pod_count", "node_cpu_pct") != "available":
        return None
    pods = fact_value(cluster, "pod_count")
    cpu = cpu_pct(cluster) or fact_value(cluster, "node_cpu_pct")
    if pods is None or cpu is None:
        return None
    if float(cpu) >= th["node_cpu_downsize_pct"] or float(pods) >= th["pod_density_low"]:
        return None
    name = cluster.get("name") or ""
    savings = estimate_instance_pool_savings(
        monthly_cost,
        instance_hourly_usd=aks_node_hourly_baseline(),
        capacity=int(fact_value(cluster, "node_count") or 3),
        savings_factor=0.20,
        min_savings=th["min_savings"],
    )
    return ComputeFindingDraft(
        rule_id="AKS_POD_DENSITY_EXTENDED",
        detail=(
            f"AKS cluster '{name}' runs {int(pods)} pods with {float(cpu):.1f}% average node CPU — "
            "low pod density may indicate over-provisioned nodes."
        ),
        recommendation="Consolidate workloads, enable cluster autoscaler, or reduce node pool size after validating HA requirements.",
        savings=savings,
        waste_score=54,
        confidence=confidence_with_monitor(72, cluster),
        priority="P2",
        impact="Node pool consolidation can reduce agent VM charges",
        evidence=structured_evidence(
            cluster,
            determination="low_pod_density",
            summary="Low pod count relative to node CPU suggests consolidation opportunity.",
            checks=[
                make_check("Pod count", pods, f"< {th['pod_density_low']:.0f}", passed=True),
                make_check("Node CPU %", cpu, f"< {th['node_cpu_downsize_pct']:.0f}%", passed=True),
            ],
            extra={"monthly_cost_usd": monthly_cost},
        ),
    )
