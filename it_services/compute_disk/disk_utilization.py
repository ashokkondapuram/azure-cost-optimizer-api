"""Disk IOPS and throughput utilization helpers for cost and performance rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.managed_disk_catalog import optimization_thresholds, resolve_disk_provisioned_performance
from app.metrics_triggers import TRAFFIC_THRESHOLDS
from app.resource_utilization import fact_value, monitor_facts_status, technical_facts


def _props(disk: dict[str, Any] | None) -> dict[str, Any]:
    if not disk:
        return {}
    return dict(disk.get("properties") or {})


def provisioned_iops(disk: dict[str, Any] | None = None, *, resource: dict[str, Any] | None = None) -> float | None:
    """Provisioned IOPS cap from ARM properties or Azure tier size table."""
    if disk:
        perf = resolve_disk_provisioned_performance(disk)
        val = perf.get("diskIOPSReadWrite")
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    if resource:
        val = fact_value(resource, "provisioned_iops")
        if val is not None:
            return val
    return None


def provisioned_mbps(disk: dict[str, Any] | None = None, *, resource: dict[str, Any] | None = None) -> float | None:
    """Provisioned throughput cap in MB/s from ARM or tier size table."""
    if disk:
        perf = resolve_disk_provisioned_performance(disk)
        val = perf.get("diskMBpsReadWrite")
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    if resource:
        val = fact_value(resource, "provisioned_mbps")
        if val is not None:
            return val
    return None


def combined_disk_iops(resource: dict[str, Any]) -> float | None:
    """Observed read + write IOPS from monitor facts."""
    facts = technical_facts(resource)
    if "disk_read_iops" not in facts and "disk_write_iops" not in facts:
        return None
    read_iops = fact_value(resource, "disk_read_iops", 0.0) or 0.0
    write_iops = fact_value(resource, "disk_write_iops", 0.0) or 0.0
    return read_iops + write_iops


def combined_disk_throughput_bps(resource: dict[str, Any]) -> float | None:
    facts = technical_facts(resource)
    if "disk_read_bps" not in facts and "disk_write_bps" not in facts:
        return None
    read_bps = fact_value(resource, "disk_read_bps", 0.0) or 0.0
    write_bps = fact_value(resource, "disk_write_bps", 0.0) or 0.0
    return read_bps + write_bps


def combined_peak_disk_iops(resource: dict[str, Any]) -> float | None:
    """Peak read + write IOPS from maximum monitor aggregations."""
    facts = technical_facts(resource)
    if "max_disk_read_iops" not in facts and "max_disk_write_iops" not in facts:
        return None
    read_iops = fact_value(resource, "max_disk_read_iops", 0.0) or 0.0
    write_iops = fact_value(resource, "max_disk_write_iops", 0.0) or 0.0
    return read_iops + write_iops


def peak_disk_iops_utilization_pct(
    resource: dict[str, Any],
    disk: dict[str, Any] | None = None,
) -> float | None:
    """Peak observed IOPS as a percentage of provisioned diskIOPSReadWrite."""
    observed = combined_peak_disk_iops(resource)
    cap = provisioned_iops(disk, resource=resource)
    if observed is None or cap is None or cap <= 0:
        return None
    return round((observed / cap) * 100.0, 4)


def disk_iops_utilization_pct(
    resource: dict[str, Any],
    disk: dict[str, Any] | None = None,
) -> float | None:
    """Observed IOPS as a percentage of provisioned diskIOPSReadWrite."""
    observed = combined_disk_iops(resource)
    cap = provisioned_iops(disk, resource=resource)
    if observed is None or cap is None or cap <= 0:
        return None
    return round((observed / cap) * 100.0, 4)


def disk_throughput_utilization_pct(
    resource: dict[str, Any],
    disk: dict[str, Any] | None = None,
) -> float | None:
    """Observed bytes/sec as a percentage of provisioned diskMBpsReadWrite."""
    observed_bps = combined_disk_throughput_bps(resource)
    cap_mbps = provisioned_mbps(disk, resource=resource)
    if observed_bps is None or cap_mbps is None or cap_mbps <= 0:
        return None
    cap_bps = cap_mbps * 1_000_000.0
    return round((observed_bps / cap_bps) * 100.0, 4)


def is_low_disk_iops_utilization(
    resource: dict[str, Any],
    disk: dict[str, Any] | None = None,
    *,
    threshold_pct: float | None = None,
) -> bool | None:
    """True when observed IOPS are well below the provisioned cap (downgrade candidate)."""
    util = disk_iops_utilization_pct(resource, disk)
    if util is None:
        return None
    threshold = threshold_pct if threshold_pct is not None else TRAFFIC_THRESHOLDS["disk_iops_low_util_pct"]
    return util < threshold


def metrics_block_disk_downgrade(
    resource: dict[str, Any],
    disk: dict[str, Any] | None = None,
    *,
    threshold_pct: float | None = None,
) -> bool:
    """Skip tier downgrade when monitor data shows sustained or peak IOPS near the cap."""
    peak_util = peak_disk_iops_utilization_pct(resource, disk)
    if peak_util is not None:
        threshold = threshold_pct if threshold_pct is not None else 50.0
        return peak_util >= threshold
    util = disk_iops_utilization_pct(resource, disk)
    if util is None:
        return False
    threshold = threshold_pct if threshold_pct is not None else TRAFFIC_THRESHOLDS["disk_iops_block_downgrade_pct"]
    return util >= threshold


def is_disk_underprovisioned(
    resource: dict[str, Any],
    disk: dict[str, Any] | None = None,
    *,
    threshold_pct: float | None = None,
) -> bool | None:
    """True when observed IOPS or throughput exceed safe headroom on the provisioned tier."""
    iops_util = disk_iops_utilization_pct(resource, disk)
    throughput_util = disk_throughput_utilization_pct(resource, disk)
    if iops_util is None and throughput_util is None:
        return None
    threshold = threshold_pct if threshold_pct is not None else TRAFFIC_THRESHOLDS["disk_iops_high_util_pct"]
    if iops_util is not None and iops_util >= threshold:
        return True
    if throughput_util is not None and throughput_util >= threshold:
        return True
    if iops_util is None and throughput_util is None:
        return None
    return False


def disk_utilization_evidence(
    resource: dict[str, Any],
    disk: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inventory caps and computed utilization for finding evidence."""
    out: dict[str, Any] = {}
    cap_iops = provisioned_iops(disk, resource=resource)
    cap_mbps = provisioned_mbps(disk, resource=resource)
    if cap_iops is not None:
        out["provisioned_iops"] = cap_iops
    if cap_mbps is not None:
        out["provisioned_mbps"] = cap_mbps
    iops_util = disk_iops_utilization_pct(resource, disk)
    if iops_util is not None:
        out["disk_iops_utilization_pct"] = iops_util
    throughput_util = disk_throughput_utilization_pct(resource, disk)
    if throughput_util is not None:
        out["disk_throughput_utilization_pct"] = throughput_util
    combined_iops = combined_disk_iops(resource)
    if combined_iops is not None:
        out["disk_combined_iops"] = combined_iops
    return out


def disk_utilization_gate(
    resource: dict[str, Any],
    *required_metrics: str,
    allow_inventory_only: bool = True,
) -> bool:
    """Disk-specific gate allowing partial metrics (unlike strict utilization_gate).

    Returns True when disk analysis should proceed based on available metrics.
    - If ANY required metric is available → True
    - If no metrics available → True if allow_inventory_only, else False
    - Gracefully handles partial data instead of blocking
    """
    facts = technical_facts(resource)

    # Check if any required metric exists
    if required_metrics:
        for metric in required_metrics:
            if metric in facts:
                return True

    # No required metrics found - check if we should allow inventory-only analysis
    status = monitor_facts_status(resource, *required_metrics)
    if status == "no_monitor":
        return allow_inventory_only

    return False


def validate_disk_metrics(
    resource: dict[str, Any],
    max_age_days: int = 30,
) -> tuple[bool, Optional[str]]:
    """Validate disk metrics quality and timeliness.

    Returns: (is_valid, reason_if_invalid)
    """
    facts = technical_facts(resource)

    # Check if any metrics exist
    disk_metrics = {
        "disk_read_iops", "disk_write_iops", "disk_read_bps", "disk_write_bps",
        "disk_paid_burst_iops",
    }
    has_metrics = any(m in facts for m in disk_metrics)

    if not has_metrics:
        return True, None  # No metrics is ok, just means inventory-only analysis

    # Check metric values are within realistic ranges
    for metric in ["disk_read_iops", "disk_write_iops"]:
        val = fact_value(resource, metric)
        if val is not None and (val < 0 or val > 160000):
            return False, f"{metric} out of range: {val}"

    for metric in ["disk_read_bps", "disk_write_bps"]:
        val = fact_value(resource, metric)
        if val is not None and (val < 0 or val > (2000 * 1_000_000)):
            return False, f"{metric} out of range: {val}"

    burst_ops = fact_value(resource, "disk_paid_burst_iops")
    if burst_ops is not None and burst_ops < 0:
        return False, f"disk_paid_burst_iops out of range: {burst_ops}"

    # Check metric age
    metrics_timestamp = fact_value(resource, "_metrics_timestamp")
    if metrics_timestamp is not None:
        try:
            if isinstance(metrics_timestamp, str):
                ts = datetime.fromisoformat(metrics_timestamp.replace('Z', '+00:00'))
            else:
                ts = datetime.fromtimestamp(metrics_timestamp, tz=timezone.utc)

            age = datetime.now(timezone.utc) - ts
            if age > timedelta(days=max_age_days):
                return True, f"Metrics stale: {age.days} days old (last updated {ts.isoformat()})"
        except (ValueError, TypeError):
            pass

    return True, None


def check_metric_staleness(
    resource: dict[str, Any],
    max_age_days: int = 30,
) -> Optional[str]:
    """Check if metrics are stale and return warning message if so."""
    metrics_timestamp = fact_value(resource, "_metrics_timestamp")
    if metrics_timestamp is None:
        return None

    try:
        if isinstance(metrics_timestamp, str):
            ts = datetime.fromisoformat(metrics_timestamp.replace('Z', '+00:00'))
        else:
            ts = datetime.fromtimestamp(metrics_timestamp, tz=timezone.utc)

        age = datetime.now(timezone.utc) - ts
        if age > timedelta(days=max_age_days):
            days_old = age.days
            return f"⚠️ Metrics are {days_old} days old (last updated {ts.isoformat()}). Recommendation may not reflect current state."

        return None
    except (ValueError, TypeError):
        return None


def metrics_status(resource: dict[str, Any]) -> str:
    """Determine overall metrics status for a disk."""
    facts = technical_facts(resource)
    disk_metrics = {
        "disk_read_iops", "disk_write_iops", "disk_read_bps", "disk_write_bps",
        "disk_paid_burst_iops",
    }

    has_metrics = sum(1 for m in disk_metrics if m in facts)

    if has_metrics == 0:
        return "none"
    elif has_metrics < len(disk_metrics):
        return "partial"
    else:
        return "available"
