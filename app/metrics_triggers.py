"""Metric trigger registry — thresholds, cost vs performance effects, and rule linkage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MetricTrigger:
    fact_key: str
    direction: str  # low | high | idle | both
    threshold: str
    effect_cost: str
    effect_performance: str
    rules: tuple[str, ...]
    safety_gate: str = ""


METRIC_TRIGGERS: dict[str, MetricTrigger] = {
    "avg_cpu_pct": MetricTrigger(
        fact_key="avg_cpu_pct",
        direction="both",
        threshold="< 5% idle · < 20% low · > 85% high",
        effect_cost="Low CPU enables idle VM removal and rightsizing savings (up to 90% MTD).",
        effect_performance="High CPU blocks downsize; sustained high utilization signals capacity risk.",
        rules=(
            "VM_IDLE", "VM_OVERSIZE", "VM_UNDERUTILIZED_EXTENDED",
            "VM_SKU_SIZING_EXTENDED", "VM_RIGHTSIZE_FAMILY", "VMSS_NONPROD_SCHEDULING_EXTENDED",
        ),
        safety_gate="Downsize blocked when CPU ≥ 60% or memory ≥ 80%.",
    ),
    "avg_memory_pct": MetricTrigger(
        fact_key="avg_memory_pct",
        direction="both",
        threshold="< 30% downsize candidate · > 85% upsize candidate",
        effect_cost="Low memory supports SKU downgrade and cross-family rightsizing.",
        effect_performance="High memory blocks downsize and may require upsize.",
        rules=("VM_OVERSIZE", "VM_SKU_SIZING_EXTENDED", "VM_RIGHTSIZE_FAMILY", "VMSS_NONPROD_SCHEDULING_EXTENDED"),
        safety_gate="Downsize blocked when memory ≥ 80%.",
    ),
    "cluster_cpu_pct": MetricTrigger(
        fact_key="cluster_cpu_pct",
        direction="low",
        threshold="< 10% per node / cluster",
        effect_cost="Idle AKS nodes can be scaled down for proportional compute savings.",
        effect_performance="Very low cluster CPU indicates over-provisioned node pools.",
        rules=("AKS_IDLE_POOL_EXTENDED", "AKS_NODE_IDLE"),
    ),
    "cluster_mem_pct": MetricTrigger(
        fact_key="cluster_mem_pct",
        direction="low",
        threshold="< 15% per node",
        effect_cost="Supports idle node pool reduction recommendations.",
        effect_performance="Low memory headroom may still be required for burst workloads.",
        rules=("AKS_IDLE_POOL_EXTENDED", "AKS_NODE_IDLE"),
    ),
    "disk_read_bps": MetricTrigger(
        fact_key="disk_read_bps",
        direction="low",
        threshold="Combined read+write < 1,024 B/s on attached premium disks",
        effect_cost="Near-zero I/O on premium disks enables tier downgrade savings.",
        effect_performance="Low I/O confirms disk is not performance-bound.",
        rules=("DISK_UNUSED_EXTENDED", "DISK_OVERSIZE_EXTENDED"),
        safety_gate="Downgrade blocked when IOPS utilization ≥ 20% of provisioned cap.",
    ),
    "disk_write_bps": MetricTrigger(
        fact_key="disk_write_bps",
        direction="low",
        threshold="Combined read+write < 1,024 B/s on attached premium disks",
        effect_cost="Near-zero I/O on premium disks enables tier downgrade savings.",
        effect_performance="Low I/O confirms disk is not performance-bound.",
        rules=("DISK_UNUSED_EXTENDED", "DISK_OVERSIZE_EXTENDED"),
        safety_gate="Downgrade blocked when IOPS utilization ≥ 20% of provisioned cap.",
    ),
    "disk_read_iops": MetricTrigger(
        fact_key="disk_read_iops",
        direction="both",
        threshold="< 20% of cap low · ≥ 80% of cap under-provisioned",
        effect_cost="Low IOPS utilization supports Premium → Standard SSD downgrade.",
        effect_performance="High IOPS utilization signals capacity risk; blocks downgrade.",
        rules=("DISK_OVERSIZE_EXTENDED", "DISK_UNDERPROVISIONED"),
        safety_gate="Downgrade blocked when combined IOPS ≥ 20% of diskIOPSReadWrite.",
    ),
    "disk_write_iops": MetricTrigger(
        fact_key="disk_write_iops",
        direction="both",
        threshold="< 20% of cap low · ≥ 80% of cap under-provisioned",
        effect_cost="Low IOPS utilization supports Premium → Standard SSD downgrade.",
        effect_performance="High IOPS utilization signals capacity risk; blocks downgrade.",
        rules=("DISK_OVERSIZE_EXTENDED", "DISK_UNDERPROVISIONED"),
        safety_gate="Downgrade blocked when combined IOPS ≥ 20% of diskIOPSReadWrite.",
    ),
    "disk_iops_utilization_pct": MetricTrigger(
        fact_key="disk_iops_utilization_pct",
        direction="both",
        threshold="< 20% downgrade candidate · ≥ 80% upsize candidate",
        effect_cost="Low utilization vs provisioned IOPS enables tier downgrade.",
        effect_performance="Sustained high utilization requires larger disk or higher tier.",
        rules=("DISK_OVERSIZE_EXTENDED", "DISK_UNDERPROVISIONED"),
        safety_gate="Downgrade blocked when utilization ≥ 20%.",
    ),
    "age_days": MetricTrigger(
        fact_key="age_days",
        direction="high",
        threshold="> snapshot_retention_days (default 90)",
        effect_cost="Stale snapshots accumulate backup storage cost; deletion recovers full MTD spend.",
        effect_performance="No workload impact when recovery requirements are validated.",
        rules=("SNAPSHOT_OLD", "SNAPSHOT_RETENTION_EXTENDED"),
        safety_gate="Size gate (snapshot_min_size_gb) and min_monthly_savings_usd on extended rule.",
    ),
    "byte_count": MetricTrigger(
        fact_key="byte_count",
        direction="low",
        threshold="< 1,000,000 bytes in period",
        effect_cost="Low traffic on public IPs, NAT gateways, and load balancers may be removable.",
        effect_performance="Minimal traffic indicates no active workload dependency.",
        rules=("PUBLIC_IP_IDLE_EXTENDED", "NAT_GATEWAY_IDLE_EXTENDED", "LOAD_BALANCER_IDLE_EXTENDED"),
    ),
    "throughput_bytes": MetricTrigger(
        fact_key="throughput_bytes",
        direction="low",
        threshold="< 500 bytes",
        effect_cost="Idle Application Gateway may be deleted for fixed-cost savings (~40% MTD).",
        effect_performance="Low throughput confirms gateway is not serving meaningful traffic.",
        rules=("APP_GATEWAY_IDLE_EXTENDED",),
    ),
    "request_count": MetricTrigger(
        fact_key="request_count",
        direction="low",
        threshold="< 1,000 requests (AppGW) · < 500 (App Service)",
        effect_cost="Low request volume supports plan downgrade or resource removal.",
        effect_performance="Low traffic reduces performance tuning urgency.",
        rules=("APP_GATEWAY_IDLE_EXTENDED", "APP_SERVICE_PLAN_EXTENDED"),
    ),
    "transaction_count": MetricTrigger(
        fact_key="transaction_count",
        direction="low",
        threshold="< 5,000 transactions",
        effect_cost="Low transaction volume supports storage lifecycle / tier optimization.",
        effect_performance="Infrequent access patterns suit cool or archive tiers.",
        rules=("STORAGE_NO_LIFECYCLE", "STORAGE_LIFECYCLE_EXTENDED"),
    ),
    "used_capacity_bytes": MetricTrigger(
        fact_key="used_capacity_bytes",
        direction="low",
        threshold="Low used capacity vs provisioned (< 25% when capacity known)",
        effect_cost="Underused storage capacity supports tier and lifecycle policies.",
        effect_performance="Capacity headroom is healthy unless paired with high transaction load.",
        rules=("STORAGE_NO_LIFECYCLE", "STORAGE_LIFECYCLE_EXTENDED"),
    ),
    "cpu_pct": MetricTrigger(
        fact_key="cpu_pct",
        direction="low",
        threshold="< 10% (SQL serverless candidate)",
        effect_cost="Low SQL CPU supports serverless or lower tier migration.",
        effect_performance="Sustained high CPU requires scale-up before cost reduction.",
        rules=("SQL_SERVERLESS_EXTENDED",),
    ),
    "storage_pct": MetricTrigger(
        fact_key="storage_pct",
        direction="low",
        threshold="< 40% (PostgreSQL storage)",
        effect_cost="Low storage utilization supports storage tier reduction.",
        effect_performance="Monitor growth before reducing provisioned storage.",
        rules=("POSTGRESQL_STORAGE_EXTENDED",),
    ),
    "memory_pct": MetricTrigger(
        fact_key="memory_pct",
        direction="both",
        threshold="< 35% downsize · blocked if ≥ 80%",
        effect_cost="Low Redis memory supports smaller cache SKU.",
        effect_performance="High memory or ops/sec blocks downsize.",
        rules=("REDIS_RIGHTSIZE_EXTENDED",),
    ),
    "total_ru": MetricTrigger(
        fact_key="total_ru",
        direction="low",
        threshold="< 50,000 RU",
        effect_cost="Low RU consumption supports autoscale or manual throughput reduction.",
        effect_performance="Low RU indicates light workload; watch for latency before reducing.",
        rules=("COSMOS_AUTOSCALE_EXTENDED",),
    ),
    "api_hits": MetricTrigger(
        fact_key="api_hits",
        direction="both",
        threshold="< kv_api_hits_idle idle · ≥ kv_api_hits_high high-ops",
        effect_cost="Idle vaults may be deleted; high volume increases per-operation charges.",
        effect_performance="Low hits indicate no dependency; high hits may need caching not capacity change.",
        rules=("KEYVAULT_IDLE_EXTENDED", "KEYVAULT_PREMIUM_EXTENDED", "KEYVAULT_HIGH_OPS_EXTENDED"),
    ),
    "pull_count": MetricTrigger(
        fact_key="pull_count",
        direction="low",
        threshold="< acr_pull_count_low (default 500)",
        effect_cost="Low pull volume supports Basic tier ACR instead of Premium.",
        effect_performance="Low pulls confirm registry is not on a hot deployment path.",
        rules=("ACR_PREMIUM_EXTENDED", "ACR_STANDARD_EXTENDED", "ACR_STORAGE_HIGH_EXTENDED"),
        safety_gate="SKU downgrade blocked when Premium-only features are active.",
    ),
    "push_count": MetricTrigger(
        fact_key="push_count",
        direction="low",
        threshold="< acr_push_count_low (default 100)",
        effect_cost="Low push volume with high storage supports image cleanup recommendations.",
        effect_performance="Low push activity indicates infrequent CI/CD use.",
        rules=("ACR_STORAGE_HIGH_EXTENDED",),
    ),
    "storage_used_bytes": MetricTrigger(
        fact_key="storage_used_bytes",
        direction="high",
        threshold=">= acr_storage_high_gb (default 50 GB)",
        effect_cost="High registry storage increases ongoing backup and tier costs.",
        effect_performance="Storage pressure may slow pulls; cleanup reduces bloat.",
        rules=("ACR_STORAGE_HIGH_EXTENDED", "ACR_RETENTION_DISABLED_EXTENDED", "ACR_STANDARD_EXTENDED"),
        safety_gate="Standard→Basic blocked when storage exceeds high threshold.",
    ),
    "throttled_search_pct": MetricTrigger(
        fact_key="throttled_search_pct",
        direction="high",
        threshold="Elevated throttling indicates capacity pressure",
        effect_cost="Scaling up search replicas increases cost but may be required.",
        effect_performance="High throttling degrades query performance — scale or optimize queries.",
        rules=(),
    ),
    "backend_availability_pct": MetricTrigger(
        fact_key="backend_availability_pct",
        direction="low",
        threshold="Low backend availability",
        effect_cost="Removing idle load balancer saves cost only when backends are empty.",
        effect_performance="Low availability indicates unhealthy backends — fix before removal.",
        rules=("LOAD_BALANCER_IDLE_EXTENDED",),
    ),
    "monthly_cost_usd": MetricTrigger(
        fact_key="monthly_cost_usd",
        direction="high",
        threshold="Drives savings estimates for all cost rules",
        effect_cost="Higher MTD cost increases absolute savings from optimization actions.",
        effect_performance="Cost alone does not indicate performance risk.",
        rules=("FIREWALL_FIXED_COST_EXTENDED", "CDN_PROFILE_COST_EXTENDED"),
    ),
}

# Network / traffic thresholds centralized from resource_utilization.py
TRAFFIC_THRESHOLDS = {
    "byte_count_low": 1_000_000,
    "packet_count_low": 100,
    "throughput_bytes_low": 500,
    "request_count_low": 1_000,
    "transaction_count_low": 5_000,
    "api_hits_low": 10,
    "pull_count_low": 500,
    "acr_pull_count_low": 500,
    "acr_storage_high_gb": 50,
    "acr_push_count_low": 100,
    "kv_api_hits_idle": 10,
    "kv_api_hits_high": 50_000,
    "total_ru_low": 50_000,
    "disk_io_idle_bps": 1024,
    "disk_iops_low_util_pct": 20,
    "disk_iops_high_util_pct": 80,
    "disk_iops_block_downgrade_pct": 20,
    "snapshot_retention_days_default": 90,
    "snapshot_min_size_gb": 0,
    "cpu_idle_pct": 5,
    "cpu_oversize_pct": 20,
    "cpu_high_pct": 85,
    "memory_idle_pct": 30,
    "memory_high_pct": 80,
    "rightsizing_block_cpu_pct": 60,
    "rightsizing_block_memory_pct": 80,
}


def triggers_for_fact_key(fact_key: str) -> MetricTrigger | None:
    return METRIC_TRIGGERS.get(fact_key)


def triggers_for_rule(rule_id: str) -> list[MetricTrigger]:
    rid = (rule_id or "").upper()
    return [t for t in METRIC_TRIGGERS.values() if rid in t.rules]


def triggers_for_metrics(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach trigger context to unified metric rows."""
    out: list[dict[str, Any]] = []
    for row in metrics:
        trigger = triggers_for_fact_key(row.get("fact_key") or "")
        if not trigger:
            out.append({**row, "trigger": None})
            continue
        out.append({
            **row,
            "trigger": {
                "direction": trigger.direction,
                "threshold": trigger.threshold,
                "effect_cost": trigger.effect_cost,
                "effect_performance": trigger.effect_performance,
                "rules": list(trigger.rules),
                "safety_gate": trigger.safety_gate or None,
            },
        })
    return out


def trigger_reason_for_finding(rule_id: str, evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """Build trigger metric summaries for recommendation cards."""
    triggers = triggers_for_rule(rule_id)
    if not triggers:
        return []
    perf = (evidence.get("optimization_metrics") or {}).get("performance") or []
    perf_by_id = {m.get("id"): m for m in perf if isinstance(m, dict)}
    reasons: list[dict[str, Any]] = []
    for trigger in triggers:
        defn = None
        for m in perf:
            if not isinstance(m, dict):
                continue
            if m.get("id") and trigger.fact_key in str(m.get("id")):
                defn = m
                break
            if m.get("label", "").lower().find(trigger.fact_key.replace("_", " ")) >= 0:
                defn = m
                break
        value = None
        status = None
        if defn:
            value = defn.get("value")
            status = defn.get("status")
        else:
            for key in (trigger.fact_key, trigger.fact_key.replace("_pct", "_percent")):
                if key in evidence:
                    value = evidence[key]
                    break
        reasons.append({
            "fact_key": trigger.fact_key,
            "label": (defn or {}).get("label") or trigger.fact_key.replace("_", " ").title(),
            "value": value,
            "status": status,
            "threshold": trigger.threshold,
            "direction": trigger.direction,
            "effect_cost": trigger.effect_cost,
            "effect_performance": trigger.effect_performance,
            "safety_gate": trigger.safety_gate or None,
        })
    return reasons


def generate_metrics_triggers_markdown() -> str:
    """Human-readable matrix for docs/METRICS_AND_TRIGGERS.md."""
    lines = [
        "# Metrics and triggers",
        "",
        "Generated from `app/metrics_triggers.py`. Do not edit by hand.",
        "",
        "| Metric | Direction | Threshold | Cost effect | Performance effect | Rules |",
        "|--------|-----------|-----------|-------------|-------------------|-------|",
    ]
    for trigger in sorted(METRIC_TRIGGERS.values(), key=lambda t: t.fact_key):
        rules = ", ".join(trigger.rules[:3])
        if len(trigger.rules) > 3:
            rules += f" (+{len(trigger.rules) - 3})"
        lines.append(
            f"| `{trigger.fact_key}` | {trigger.direction} | {trigger.threshold} | "
            f"{trigger.effect_cost} | {trigger.effect_performance} | {rules or '—'} |"
        )
    lines.extend([
        "",
        "## Centralized thresholds",
        "",
        "| Key | Value |",
        "|-----|-------|",
    ])
    for key, val in sorted(TRAFFIC_THRESHOLDS.items()):
        lines.append(f"| `{key}` | {val} |")
    lines.append("")
    return "\n".join(lines)
