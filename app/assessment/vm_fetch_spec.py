"""VM inventory, metrics, and cost fetch configuration from vm-assessment.json."""

from __future__ import annotations

from app.assessment.bridge import (
    arm_property_paths,
    cost_field_mapping,
    load_assessment_for_canonical,
    metrics_period_default,
    optimization_thresholds,
    sync_property_paths,
)
from app.assessment.spec import monitor_metric_names, required_metric_keys

CANONICAL_TYPE = "compute/vm"
ASSESSMENT_FILE = "vm-assessment.json"


def load_vm_assessment() -> dict:
    assessment = load_assessment_for_canonical(CANONICAL_TYPE)
    if not assessment:
        raise FileNotFoundError(f"{ASSESSMENT_FILE} not indexed for {CANONICAL_TYPE}")
    return assessment


def vm_sync_property_paths() -> tuple[str, ...]:
    return sync_property_paths(load_vm_assessment())


def vm_arm_property_paths() -> tuple[str, ...]:
    return arm_property_paths(load_vm_assessment())


def vm_metrics_period_default() -> str:
    return metrics_period_default(load_vm_assessment())


def vm_monitor_metric_names() -> tuple[str, ...]:
    return monitor_metric_names(load_vm_assessment())


def vm_required_metric_keys() -> list[str]:
    return required_metric_keys(load_vm_assessment())


def vm_optimization_thresholds() -> dict[str, float]:
    return optimization_thresholds(load_vm_assessment())


def vm_cost_field_mapping() -> dict[str, str]:
    return cost_field_mapping(load_vm_assessment())
