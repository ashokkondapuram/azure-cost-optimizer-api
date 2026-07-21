"""Backward-compatible shim — use app.resources.registry instead."""

from app.resources import (
    RESOURCE_MONITOR_PROFILES,
    ResourceMonitorProfile,
    UtilizationMetric,
    attach_utilization_metrics,
    get_monitor_profile,
    list_monitor_profiles,
    monitor_arm_type,
    profiles_for_canonical,
    to_usage_metric_defs,
    usage_metrics_for_canonical,
)

__all__ = [
    "RESOURCE_MONITOR_PROFILES",
    "ResourceMonitorProfile",
    "UtilizationMetric",
    "attach_utilization_metrics",
    "get_monitor_profile",
    "list_monitor_profiles",
    "monitor_arm_type",
    "profiles_for_canonical",
    "to_usage_metric_defs",
    "usage_metrics_for_canonical",
]
