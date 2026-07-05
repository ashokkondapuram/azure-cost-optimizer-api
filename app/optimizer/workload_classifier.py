"""Classify workload type from monitor facts and tags (2-B)."""

from __future__ import annotations

from typing import Literal

from app.resource_utilization import fact_value, peak_cpu_ok_for_downsize

WorkloadClass = Literal["batch", "interactive", "database", "analytics", "idle", "zombie"]


def classify_workload(
    resource: dict,
    facts: dict[str, float] | None = None,
    *,
    resource_type: str = "",
) -> WorkloadClass:
    """Classify a resource workload from utilization facts and governance tags."""
    facts = facts or {}
    tags = resource.get("tags") or {}
    if not isinstance(tags, dict):
        tags = {}

    avg_cpu = float(facts.get("avg_cpu_pct") or 0)
    max_cpu = float(facts.get("max_cpu_pct") or avg_cpu)
    avg_iops = float(facts.get("avg_disk_iops") or facts.get("avg_disk_iops_utilization_pct") or 0)
    net = float(facts.get("avg_bytes_sent_rate") or facts.get("avg_network_out_mbps") or 0)

    burstiness = (max_cpu - avg_cpu) / max(avg_cpu, 1.0)

    if avg_cpu < 2 and avg_iops < 100 and net < 1000:
        return "zombie"
    if avg_cpu < 5:
        return "idle"
    if burstiness > 3.0:
        return "batch"
    if avg_iops > avg_cpu * 50 and avg_cpu > 0:
        return "database"
    if net > max(avg_cpu * 10000, 5000):
        return "interactive"
    if avg_cpu > 50 and avg_iops > avg_cpu * 20:
        return "analytics"
    if "database" in (resource_type or "").lower() or "sql" in (resource_type or "").lower():
        return "database"
    return "interactive"


def classify_workloads_for_buckets(
    buckets: dict[str, list],
    resource_facts: dict[str, dict[str, float]] | None = None,
) -> dict[str, WorkloadClass]:
    """Return {normalized_resource_id: workload_class} for all bucket resources."""
    from app.focus_mapping import normalize_arm_id

    out: dict[str, WorkloadClass] = {}
    facts_map = resource_facts or {}
    for items in (buckets or {}).values():
        for resource in items or []:
            rid = normalize_arm_id(resource.get("id") or "").lower()
            if not rid:
                continue
            out[rid] = classify_workload(
                resource,
                facts_map.get(rid) or resource.get("_technical_facts") or {},
                resource_type=str(resource.get("type") or resource.get("resource_type") or ""),
            )
    return out


def downsize_allowed_for_workload(
    workload_class: str,
    facts: dict[str, float] | None,
    *,
    avg_threshold: float,
) -> bool:
    """Workload-aware downsize gate — batch uses peak only; interactive needs headroom."""
    facts = facts or {}
    wrapper = {"_technical_facts": facts}
    avg_cpu = float(fact_value(wrapper, "avg_cpu_pct") or 0)
    max_cpu = float(fact_value(wrapper, "max_cpu_pct") or avg_cpu)

    if workload_class in ("zombie", "idle"):
        return False
    if workload_class == "batch":
        return max_cpu < avg_threshold
    if workload_class == "interactive":
        return avg_cpu < avg_threshold * 0.85 and max_cpu < avg_threshold
    if workload_class == "database":
        avg_mem = float(facts.get("avg_memory_pct") or 0)
        avg_iops = float(
            facts.get("avg_disk_iops_utilization_pct")
            or facts.get("max_disk_iops_utilization_pct")
            or 0
        )
        return (
            avg_mem < 75
            and avg_iops < 70
            and peak_cpu_ok_for_downsize(wrapper, avg_threshold=avg_threshold)
        )
    return peak_cpu_ok_for_downsize(wrapper, avg_threshold=avg_threshold)


def is_zombie_workload(workload_class: str) -> bool:
    return workload_class == "zombie"
