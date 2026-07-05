"""Per-resource technical fetch and utilization metric definitions."""

from app.resources.extraction import (
    extract_technical_facts,
    list_technical_fetch_specs,
    pick_sync_properties,
)
from app.resources.registry import (
    RESOURCE_MONITOR_PROFILES,
    TECHNICAL_FETCH_SPECS,
    attach_utilization_metrics,
    generic_arm_sync_types,
    get_monitor_profile,
    get_technical_fetch_spec,
    get_technical_fetch_spec_by_arm,
    list_monitor_profiles,
    monitor_arm_type,
    profiles_for_canonical,
    to_usage_metric_defs,
    usage_metrics_for_canonical,
)
from app.resources.types import (
    ResourceMonitorProfile,
    TechnicalFetchSpec,
    TechnicalFieldDef,
    UsageMetricDef,
    UtilizationMetric,
    field,
    metric,
    sku_text,
    utilization_metric,
)

__all__ = [
    "RESOURCE_MONITOR_PROFILES",
    "TECHNICAL_FETCH_SPECS",
    "ResourceMonitorProfile",
    "TechnicalFetchSpec",
    "TechnicalFieldDef",
    "UsageMetricDef",
    "UtilizationMetric",
    "attach_utilization_metrics",
    "extract_technical_facts",
    "field",
    "generic_arm_sync_types",
    "get_monitor_profile",
    "get_technical_fetch_spec",
    "get_technical_fetch_spec_by_arm",
    "list_monitor_profiles",
    "list_technical_fetch_specs",
    "metric",
    "monitor_arm_type",
    "pick_sync_properties",
    "profiles_for_canonical",
    "sku_text",
    "to_usage_metric_defs",
    "usage_metrics_for_canonical",
    "utilization_metric",
]
