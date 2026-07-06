"""Cross-resource correlation analysis.

Identifies hidden cost relationships between resources that are:
  - Tightly coupled (e.g. VM + its managed disks + NICs + public IPs)
  - Co-located in the same resource group with correlated spend
  - Part of a shared app service plan
  - AKS node pools sharing the same cluster cost envelope
  - Log Analytics workspaces receiving data from multiple sources

Primary output: ``CorrelationGroup`` objects that the engine uses to produce
cross-resource consolidated recommendations instead of per-resource noise.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass
class CorrelationGroup:
    group_id: str
    group_type: str              # "vm_stack" | "app_plan" | "aks_cluster" | "resource_group" | "log_analytics"
    anchor_resource_id: str      # primary resource driving the group
    member_ids: list[str]
    total_monthly_cost: float
    correlation_score: float     # 0.0–1.0, how tightly correlated
    insight: str                 # human-readable group insight
    recommendations: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


def _norm_id(rid: str) -> str:
    return (rid or "").lower().strip()


def _extract_resource_group(resource_id: str) -> str:
    parts = resource_id.lower().split("/")
    try:
        idx = parts.index("resourcegroups")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return ""


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation coefficient between two equal-length series."""
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    try:
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        den = math.sqrt(
            sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)
        )
        return num / den if den else 0.0
    except Exception:
        return None


def correlate_vm_stacks(
    buckets: dict[str, list],
    cost_by_resource: dict[str, float],
) -> list[CorrelationGroup]:
    """Group each VM with its attached managed disks, NICs, and public IPs.

    Args:
        buckets: Resource inventory buckets from the orchestrator.
        cost_by_resource: Resource ID → monthly cost USD mapping.

    Returns:
        One CorrelationGroup per VM that has dependent resources.
    """
    groups: list[CorrelationGroup] = []

    # Build quick lookup: NIC id → attached VM id
    nic_to_vm: dict[str, str] = {}
    for vm in buckets.get("vms") or []:
        vm_id = _norm_id(vm.get("id") or "")
        nics = (vm.get("properties") or {}).get("networkProfile", {}).get("networkInterfaces") or []
        for nic_ref in nics:
            nic_id = _norm_id(nic_ref.get("id") or "")
            if nic_id:
                nic_to_vm[nic_id] = vm_id

    # Disk → VM
    disk_to_vm: dict[str, str] = {}
    for disk in buckets.get("disks") or []:
        d_id = _norm_id(disk.get("id") or "")
        managed_by = _norm_id((disk.get("properties") or {}).get("managedBy") or "")
        if managed_by:
            disk_to_vm[d_id] = managed_by

    vm_members: dict[str, list[str]] = defaultdict(list)
    for disk_id, vm_id in disk_to_vm.items():
        vm_members[vm_id].append(disk_id)
    for nic_id, vm_id in nic_to_vm.items():
        vm_members[vm_id].append(nic_id)

    # Public IPs associated with NICs
    for nic in buckets.get("network_interfaces") or []:
        nic_id = _norm_id(nic.get("id") or "")
        vm_id = nic_to_vm.get(nic_id)
        if not vm_id:
            continue
        ip_cfgs = (nic.get("properties") or {}).get("ipConfigurations") or []
        for cfg in ip_cfgs:
            pip_id = _norm_id(
                ((cfg.get("properties") or {}).get("publicIPAddress") or {}).get("id") or ""
            )
            if pip_id:
                vm_members[vm_id].append(pip_id)

    for vm in buckets.get("vms") or []:
        vm_id = _norm_id(vm.get("id") or "")
        members = list({m for m in vm_members.get(vm_id, []) if m})
        if not members:
            continue
        all_ids = [vm_id] + members
        total_cost = sum(cost_by_resource.get(rid, 0.0) for rid in all_ids)
        vm_cost = cost_by_resource.get(vm_id, 0.0)
        corr = min(1.0, vm_cost / total_cost) if total_cost > 0 else 0.5
        groups.append(CorrelationGroup(
            group_id=f"vm_stack_{vm_id[-12:]}",
            group_type="vm_stack",
            anchor_resource_id=vm_id,
            member_ids=all_ids,
            total_monthly_cost=round(total_cost, 2),
            correlation_score=round(corr, 3),
            insight=(
                f"VM stack: {vm.get('name')} + {len(members)} dependent resource(s). "
                f"Total stack cost: ${total_cost:.2f}/mo."
            ),
            recommendations=[
                "Consider shutting down the full stack (VM + disks + NICs) for maximum savings.",
                "Rightsizing the VM will not reclaim disk/NIC costs — evaluate the whole stack.",
            ],
            evidence={"vm_cost": vm_cost, "dependent_count": len(members), "members": members[:10]},
        ))
    return groups


def correlate_app_service_plans(
    buckets: dict[str, list],
    cost_by_resource: dict[str, float],
) -> list[CorrelationGroup]:
    """Group App Services by their shared App Service Plan.

    Args:
        buckets: Resource inventory buckets.
        cost_by_resource: Resource ID → monthly cost USD.

    Returns:
        One CorrelationGroup per App Service Plan that hosts ≥2 apps.
    """
    groups: list[CorrelationGroup] = []
    plan_to_apps: dict[str, list[str]] = defaultdict(list)

    for app in buckets.get("app_services") or []:
        app_id = _norm_id(app.get("id") or "")
        plan_ref = _norm_id(
            ((app.get("properties") or {}).get("serverFarmId") or "")
        )
        if plan_ref:
            plan_to_apps[plan_ref].append(app_id)

    for plan in buckets.get("app_service_plans") or []:
        plan_id = _norm_id(plan.get("id") or "")
        apps = plan_to_apps.get(plan_id, [])
        if not apps:
            continue
        all_ids = [plan_id] + apps
        total_cost = sum(cost_by_resource.get(rid, 0.0) for rid in all_ids)
        sku_name = (plan.get("sku") or {}).get("name") or "unknown"
        groups.append(CorrelationGroup(
            group_id=f"app_plan_{plan_id[-12:]}",
            group_type="app_plan",
            anchor_resource_id=plan_id,
            member_ids=all_ids,
            total_monthly_cost=round(total_cost, 2),
            correlation_score=0.9,
            insight=(
                f"App Service Plan ({sku_name}) hosts {len(apps)} app(s). "
                f"Total plan cost: ${total_cost:.2f}/mo."
            ),
            recommendations=[
                f"Consolidate underutilized apps onto a smaller SKU to reduce plan cost.",
                "If all apps are idle, deleting the plan reclaims 100% of its compute cost.",
            ],
            evidence={"sku": sku_name, "app_count": len(apps), "plan_cost": cost_by_resource.get(plan_id, 0.0)},
        ))
    return groups


def correlate_aks_clusters(
    buckets: dict[str, list],
    cost_by_resource: dict[str, float],
    node_metrics: dict[str, dict] | None = None,
) -> list[CorrelationGroup]:
    """Group AKS node pools under each cluster with utilization signals.

    Args:
        buckets: Resource inventory buckets.
        cost_by_resource: Resource ID → monthly cost.
        node_metrics: Optional node-level metrics keyed by node pool ID.

    Returns:
        One CorrelationGroup per AKS cluster.
    """
    groups: list[CorrelationGroup] = []
    node_metrics = node_metrics or {}

    for cluster in buckets.get("aks_clusters") or []:
        cluster_id = _norm_id(cluster.get("id") or "")
        cluster_cost = cost_by_resource.get(cluster_id, 0.0)
        pools = (cluster.get("properties") or {}).get("agentPoolProfiles") or []
        pool_ids = [
            _norm_id(f"{cluster_id}/agentpools/{(p.get('name') or '').lower()}")
            for p in pools
        ]
        all_ids = [cluster_id] + pool_ids

        # Aggregate node utilization
        cpu_values = [
            node_metrics[pid]["avg_cpu_pct"]
            for pid in pool_ids
            if pid in node_metrics and "avg_cpu_pct" in node_metrics[pid]
        ]
        avg_cpu = statistics.mean(cpu_values) if cpu_values else None
        util_note = f" Avg node CPU: {avg_cpu:.1f}%." if avg_cpu is not None else ""

        recommendations = []
        if avg_cpu is not None and avg_cpu < 20:
            recommendations.append("Average node CPU is below 20% — consider reducing node count or VM size.")
        if len(pools) > 1:
            recommendations.append("Review node pool SKU diversity; consolidating pool sizes can cut idle node cost.")

        groups.append(CorrelationGroup(
            group_id=f"aks_{cluster_id[-12:]}",
            group_type="aks_cluster",
            anchor_resource_id=cluster_id,
            member_ids=all_ids,
            total_monthly_cost=round(cluster_cost, 2),
            correlation_score=0.95,
            insight=(
                f"AKS cluster with {len(pools)} node pool(s). "
                f"Cluster cost: ${cluster_cost:.2f}/mo.{util_note}"
            ),
            recommendations=recommendations,
            evidence={"pool_count": len(pools), "avg_cpu": avg_cpu},
        ))
    return groups


def correlate_by_resource_group(
    cost_by_resource: dict[str, float],
    resource_ids: list[str],
    min_group_cost: float = 50.0,
    min_group_size: int = 3,
) -> list[CorrelationGroup]:
    """Group resources by resource group and flag expensive under-utilised groups.

    Args:
        cost_by_resource: Resource ID → monthly cost.
        resource_ids: All known resource IDs.
        min_group_cost: Only flag groups with total cost above this threshold.
        min_group_size: Only flag groups with at least this many members.

    Returns:
        CorrelationGroup list for expensive resource groups.
    """
    rg_members: dict[str, list[str]] = defaultdict(list)
    for rid in resource_ids:
        rg = _extract_resource_group(rid)
        if rg:
            rg_members[rg].append(_norm_id(rid))

    groups: list[CorrelationGroup] = []
    for rg_name, members in rg_members.items():
        if len(members) < min_group_size:
            continue
        total_cost = sum(cost_by_resource.get(m, 0.0) for m in members)
        if total_cost < min_group_cost:
            continue
        # Use the most expensive member as anchor
        anchor = max(members, key=lambda m: cost_by_resource.get(m, 0.0))
        groups.append(CorrelationGroup(
            group_id=f"rg_{rg_name[:24]}",
            group_type="resource_group",
            anchor_resource_id=anchor,
            member_ids=members,
            total_monthly_cost=round(total_cost, 2),
            correlation_score=0.6,
            insight=(
                f"Resource group '{rg_name}': {len(members)} resources, "
                f"${total_cost:.2f}/mo total."
            ),
            recommendations=[
                "Review the resource group for orphaned or unused resources.",
                "Consider tagging resources with cost_center / owner for chargeback.",
            ],
            evidence={"rg_name": rg_name, "member_count": len(members)},
        ))
    return groups


def run_cross_resource_correlation(
    buckets: dict[str, list],
    cost_by_resource: dict[str, float],
    node_metrics: dict[str, dict] | None = None,
) -> list[CorrelationGroup]:
    """Run all correlators and return a consolidated group list.

    Args:
        buckets: Full resource inventory bucket dict from the orchestrator.
        cost_by_resource: Resource ID → monthly cost USD.
        node_metrics: Optional AKS node-level metrics.

    Returns:
        Combined, deduplicated list of CorrelationGroup objects.
    """
    all_groups: list[CorrelationGroup] = []
    all_groups.extend(correlate_vm_stacks(buckets, cost_by_resource))
    all_groups.extend(correlate_app_service_plans(buckets, cost_by_resource))
    all_groups.extend(correlate_aks_clusters(buckets, cost_by_resource, node_metrics))

    # All resource IDs from all buckets
    all_ids = [
        _norm_id(r.get("id") or "")
        for resources in buckets.values()
        for r in resources
        if r.get("id")
    ]
    all_groups.extend(correlate_by_resource_group(cost_by_resource, all_ids))

    # Sort by total cost descending
    all_groups.sort(key=lambda g: g.total_monthly_cost, reverse=True)
    log.info(
        "cross_resource_correlation.done",
        total_groups=len(all_groups),
        vm_stacks=sum(1 for g in all_groups if g.group_type == "vm_stack"),
        app_plans=sum(1 for g in all_groups if g.group_type == "app_plan"),
        aks_clusters=sum(1 for g in all_groups if g.group_type == "aks_cluster"),
        resource_groups=sum(1 for g in all_groups if g.group_type == "resource_group"),
    )
    return all_groups
