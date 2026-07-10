"""Monitor-backed utilization helpers for optimization rules across resource types."""

from __future__ import annotations

from typing import Any, Literal

MONITOR_FACT_KEYS = frozenset({
    "avg_cpu_pct",
    "avg_mem_pct",
    "avg_memory_pct",
    "max_cpu_pct",
    "max_memory_pct",
    "cpu_pct",
    "memory_pct",
    "storage_pct",
    "disk_read_bps",
    "disk_write_bps",
    "disk_read_iops",
    "disk_write_iops",
    "max_disk_read_iops",
    "max_disk_write_iops",
    "max_disk_iops_utilization_pct",
    "disk_iops_utilization_pct",
    "disk_throughput_utilization_pct",
    "byte_count",
    "throughput_bytes",
    "backend_availability_pct",
    "healthy_host_count",
    "transaction_count",
    "used_capacity_bytes",
    "pull_count",
    "push_count",
    "request_count",
    "total_ru",
    "ops_per_sec",
    "cache_hits",
    "cache_misses",
    "cache_hit_rate",
    "cache_miss_rate_pct",
    "evicted_keys",
    "expired_keys",
    "server_load_pct",
    "connected_clients",
    "error_count",
    "total_keys",
    "used_memory_rss_bytes",
    "disk_iops_pct",
    "active_connections",
    "max_connections",
    "failed_connections",
    "replication_lag_sec",
    "backup_storage_bytes",
    "connection_utilization_pct",
    "normalized_ru_pct",
    "normalized_ru_peak_pct",
    "provisioned_throughput",
    "data_usage_bytes",
    "index_usage_bytes",
    "document_count",
    "replication_latency_ms",
    "server_latency_ms",
    "ru_skew_ratio",
    "index_to_data_ratio",
    "avg_item_bytes",
    "cluster_cpu_pct",
    "cluster_mem_pct",
    "snat_connection_count",
    "http_response_ms",
    "api_hits",
    "api_results",
    "availability_pct",
    "cpu_time_sec",
    "avg_memory_bytes",
    "storage_used_bytes",
    "ingestion_gb",
    "capacity_pct",
    "runs_started",
    "runs_completed",
    "pipeline_succeeded",
    "pipeline_failed",
    "incoming_messages",
    "outgoing_messages",
    "active_messages",
    "incoming_requests",
    "search_qps",
    "throttled_search_pct",
    "ingestion_bytes",
    "query_duration_ms",
    "packet_count",
    "node_cpu_pct",
    "node_mem_pct",
    "snat_connection_count",
    "bytes_received_rate",
    "bytes_sent_rate",
})


def technical_facts(resource: dict[str, Any]) -> dict[str, Any]:
    return dict(resource.get("_technical_facts") or {})


def has_monitor_data(resource: dict[str, Any]) -> bool:
    facts = technical_facts(resource)
    if facts.get("data_source") == "azure_monitor":
        return True
    return bool(MONITOR_FACT_KEYS & facts.keys())


def fact_value(resource: dict[str, Any], key: str, default: float | None = None) -> float | None:
    val = technical_facts(resource).get(key)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def confidence_with_monitor(
    base: int,
    resource: dict[str, Any],
    *,
    boost: int = 12,
    required_keys: tuple[str, ...] = (),
) -> int:
    keys = required_keys or ()
    status = monitor_facts_status(resource, *keys) if keys else (
        "available" if has_monitor_data(resource) else "no_monitor"
    )
    if status == "available":
        return min(99, base + boost)
    if status == "partial":
        return min(PARTIAL_MONITOR_CONFIDENCE_CAP, base)
    return base


def evidence_data_source(resource: dict[str, Any], *, live_metrics: bool = False) -> str:
    if live_metrics:
        return "azure_monitor"
    facts = technical_facts(resource)
    if facts.get("data_source") == "azure_monitor":
        return "azure_monitor"
    if has_monitor_data(resource):
        return "azure_monitor"
    return "synced_inventory"


def cpu_pct(resource: dict[str, Any]) -> float | None:
    return (
        fact_value(resource, "avg_cpu_pct")
        or fact_value(resource, "cpu_pct")
        or fact_value(resource, "cluster_cpu_pct")
    )


def memory_pct(resource: dict[str, Any]) -> float | None:
    return (
        fact_value(resource, "avg_memory_pct")
        or fact_value(resource, "avg_mem_pct")
        or fact_value(resource, "memory_pct")
        or fact_value(resource, "cluster_mem_pct")
    )


def is_low_cpu(resource: dict[str, Any], threshold: float = 20.0) -> bool | None:
    value = cpu_pct(resource)
    if value is None:
        return None
    return value < threshold


def is_low_memory(resource: dict[str, Any], threshold: float = 25.0) -> bool | None:
    value = memory_pct(resource)
    if value is None:
        return None
    return value < threshold


def is_idle_io(resource: dict[str, Any], max_bps: float = 1024.0) -> bool | None:
    facts = technical_facts(resource)
    if "disk_read_bps" not in facts and "disk_write_bps" not in facts:
        return None
    read_bps = fact_value(resource, "disk_read_bps", 0.0) or 0.0
    write_bps = fact_value(resource, "disk_write_bps", 0.0) or 0.0
    return (read_bps + write_bps) < max_bps


def is_low_traffic(resource: dict[str, Any], byte_threshold: float = 1_000_000.0) -> bool | None:
    traffic = fact_value(resource, "byte_count") or fact_value(resource, "throughput_bytes")
    if traffic is None:
        return None
    return traffic < byte_threshold


def is_low_cpu_time(resource: dict[str, Any], threshold_sec: float = 3600.0) -> bool | None:
    """True when total CPU seconds over the monitor window is below threshold (web apps)."""
    value = fact_value(resource, "cpu_time_sec")
    if value is None:
        return None
    return value < threshold_sec


def webapp_utilization_summary(resource: dict[str, Any]) -> str:
    parts: list[str] = []
    cpu = cpu_pct(resource)
    if cpu is not None:
        parts.append(f"CPU {cpu:.1f}%")
    cpu_time = fact_value(resource, "cpu_time_sec")
    if cpu_time is not None:
        parts.append(f"CPU time {cpu_time:,.0f}s over 7 days")
    requests = fact_value(resource, "request_count")
    if requests is not None:
        parts.append(f"{requests:,.0f} requests over 7 days")
    return ", ".join(parts) if parts else "low activity"


def is_low_request_volume(resource: dict[str, Any], threshold: float = 1000.0) -> bool | None:
    volume = (
        fact_value(resource, "request_count")
        or fact_value(resource, "transaction_count")
        or fact_value(resource, "pull_count")
        or fact_value(resource, "total_ru")
    )
    if volume is None:
        return None
    return volume < threshold


def metrics_block_rightsize(resource: dict[str, Any], *, cpu_threshold: float = 60.0) -> bool:
    """Skip downsize recommendations when monitor data shows sustained high utilization."""
    cpu = cpu_pct(resource)
    mem = memory_pct(resource)
    if cpu is not None and cpu >= cpu_threshold:
        return True
    if mem is not None and mem >= 80.0:
        return True
    return False


def monitor_evidence(resource: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    facts = technical_facts(resource)
    out = {k: v for k, v in facts.items() if k in MONITOR_FACT_KEYS}
    out["data_source"] = evidence_data_source(resource)
    out["monitor_facts_status"] = monitor_facts_status(resource)
    out["data_quality"] = data_quality(resource)
    if extra:
        out.update(extra)
        if extra.get("data_source"):
            out["data_source"] = extra["data_source"]
    return out


MonitorFactsStatus = Literal["available", "partial", "missing", "no_monitor"]
DataQuality = Literal["full_monitor", "partial_monitor", "inventory_only"]

PARTIAL_MONITOR_CONFIDENCE_CAP = 60
VM_SIZING_FACT_KEYS = ("avg_cpu_pct", "avg_memory_pct")


def peak_cpu_ok_for_downsize(
    resource: dict[str, Any],
    *,
    avg_threshold: float,
    spike_multiplier: float = 2.5,
) -> bool:
    """True when peak CPU does not contradict an average-based downsize recommendation."""
    max_cpu = fact_value(resource, "max_cpu_pct")
    if max_cpu is None:
        return True
    return max_cpu < (avg_threshold * spike_multiplier)


def data_quality(resource: dict[str, Any], *required_keys: str) -> DataQuality:
    """Classify evidence quality for optimization findings."""
    status = monitor_facts_status(resource, *required_keys)
    if status == "available":
        return "full_monitor"
    if status in {"partial", "missing"}:
        return "partial_monitor"
    return "inventory_only"


def has_rightsizing_monitor_data(resource: dict[str, Any], *required_keys: str) -> bool:
    """True when all required monitor facts are present (strict gate for rightsizing)."""
    keys = required_keys or VM_SIZING_FACT_KEYS
    return monitor_facts_status(resource, *keys) == "available"


def monitor_facts_status(resource: dict[str, Any], *keys: str) -> MonitorFactsStatus:
    """Classify whether required monitor fact keys are present on a prepared resource."""
    if not has_monitor_data(resource):
        return "no_monitor"
    if not keys:
        return "available"
    facts = technical_facts(resource)
    present = sum(1 for key in keys if facts.get(key) is not None)
    if present == len(keys):
        return "available"
    if present == 0:
        return "missing"
    return "partial"


def has_required_facts(resource: dict[str, Any], *keys: str) -> bool:
    return monitor_facts_status(resource, *keys) == "available"


def utilization_gate(
    resource: dict[str, Any],
    *required_keys: str,
    allow_inventory_only: bool = True,
) -> bool:
    """
    Return True when a utilization-based finding should proceed.

    Skips when monitor data exists but required facts are absent (partial/missing).
  When no monitor data exists, optionally allow inventory-only findings.
    """
    status = monitor_facts_status(resource, *required_keys)
    if status == "available":
        return True
    if status == "no_monitor":
        return allow_inventory_only
    return False


def merge_vm_utilization_facts(
    resource: dict[str, Any],
    util: Any,
    *,
    vm_metrics: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Merge live VM utilization into _technical_facts for gates and evidence."""
    rid = (resource.get("id") or "").lower()
    merged_facts = dict(technical_facts(resource))
    if getattr(util, "avg_cpu_pct", None) is not None:
        merged_facts["avg_cpu_pct"] = util.avg_cpu_pct
    if getattr(util, "avg_memory_pct", None) is not None:
        merged_facts["avg_memory_pct"] = util.avg_memory_pct
    if vm_metrics and vm_metrics.get(rid):
        merged_facts["data_source"] = "azure_monitor"
    return {**resource, "_technical_facts": merged_facts}


def vm_sizing_metrics_ok(
    resource: dict[str, Any],
    util: Any,
    vm_metrics: dict[str, dict] | None = None,
) -> bool:
    """True when CPU and memory support VM SKU rightsizing (downsize or change family)."""
    if not (getattr(util, "has_cpu", False) and getattr(util, "has_memory", False)):
        return False
    rid = (resource.get("id") or "").lower()
    if vm_metrics and vm_metrics.get(rid):
        return True
    enriched = merge_vm_utilization_facts(resource, util, vm_metrics=vm_metrics)
    return utilization_gate(enriched, *VM_SIZING_FACT_KEYS, allow_inventory_only=False)


def make_check(
    signal: str,
    value: Any,
    threshold: str,
    *,
    passed: bool,
    status: str | None = None,
) -> dict[str, Any]:
    return {
        "signal": signal,
        "value": value,
        "threshold": threshold,
        "passed": passed,
        "status": status or ("pass" if passed else "fail"),
    }


def structured_evidence(
    resource: dict[str, Any],
    *,
    determination: str,
    summary: str,
    checks: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = monitor_evidence(resource, extra)
    out["determination"] = determination
    out["summary"] = summary
    out["metrics_available"] = has_monitor_data(resource)
    out["monitor_window"] = "P7D"
    if checks:
        out["checks"] = checks
    return out


def is_idle_public_ip_traffic(
    resource: dict[str, Any],
    *,
    byte_threshold: float = 1_000.0,
    packet_threshold: float = 100.0,
) -> bool | None:
    """True when associated public IP shows negligible egress in Azure Monitor."""
    bytes_val = fact_value(resource, "byte_count")
    packets = fact_value(resource, "packet_count")
    if bytes_val is None and packets is None:
        return None
    byte_idle = bytes_val is None or bytes_val < byte_threshold
    packet_idle = packets is None or packets < packet_threshold
    return byte_idle and packet_idle


def has_healthy_appgw_backends(resource: dict[str, Any], *, min_hosts: float = 1.0) -> bool | None:
    hosts = fact_value(resource, "healthy_host_count")
    if hosts is None:
        return None
    return hosts >= min_hosts


def is_low_storage_utilization(resource: dict[str, Any], threshold_pct: float = 25.0) -> bool | None:
    pct = fact_value(resource, "storage_pct")
    if pct is not None:
        return pct < threshold_pct
    used = fact_value(resource, "used_capacity_bytes")
    if used is None:
        return None
    return used <= 0


def is_idle_keyvault(resource: dict[str, Any], *, hit_threshold: float = 10.0) -> bool | None:
    from app.keyvault_utilization import is_idle_keyvault as _is_idle_keyvault

    return _is_idle_keyvault(resource, threshold=hit_threshold)


def utilization_savings_factor(
    monthly_cost: float,
    cpu: float | None,
    *,
    idle_cpu: float = 15.0,
    low_cpu: float = 30.0,
    max_factor: float = 0.5,
) -> float:
    """Estimate savings from utilization headroom instead of a flat percentage."""
    if monthly_cost <= 0:
        return 0.0
    if cpu is None:
        return round(monthly_cost * 0.25, 2)
    if cpu < idle_cpu:
        factor = max_factor
    elif cpu < low_cpu:
        factor = 0.35
    else:
        return 0.0
    return round(monthly_cost * factor, 2)
