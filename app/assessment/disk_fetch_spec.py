"""Disk inventory, metrics, and cost fetch configuration from disk-assessment.json."""

from __future__ import annotations

from it_services.compute_disk.assessment_bridge import (
    ASSESSMENT_FILE,
    billed_mtd_normalized_key,
    build_disk_monitor_profile,
    cost_field_mapping,
    disk_arm_property_paths,
    disk_cost_field_names,
    disk_cost_fields,
    disk_metric_fact_keys,
    disk_metrics_period_default,
    disk_monitor_metric_names,
    disk_monitor_metrics,
    disk_required_metric_keys,
    disk_sync_property_paths,
    load_disk_assessment,
    retail_monthly_normalized_key,
)

__all__ = [
    "ASSESSMENT_FILE",
    "billed_mtd_normalized_key",
    "build_disk_monitor_profile",
    "cost_field_mapping",
    "disk_arm_property_paths",
    "disk_cost_field_names",
    "disk_cost_fields",
    "disk_metric_fact_keys",
    "disk_metrics_period_default",
    "disk_monitor_metric_names",
    "disk_monitor_metrics",
    "disk_required_metric_keys",
    "disk_sync_property_paths",
    "load_disk_assessment",
    "retail_monthly_normalized_key",
]
