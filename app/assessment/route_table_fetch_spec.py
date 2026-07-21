"""Route table fetch configuration from route-table-assessment.json."""

from __future__ import annotations

from app.assessment.bridge import (
    arm_property_paths,
    load_assessment_by_arm,
    metrics_period_default,
    sync_property_paths,
)
from app.assessment.spec import monitor_metric_names, required_metric_keys

ARM_TYPE = "Microsoft.Network/routeTables"
ASSESSMENT_FILE = "route-table-assessment.json"
CANONICAL_TYPE = "network/routetable"


def load_route_table_assessment() -> dict:
    assessment = load_assessment_by_arm(ARM_TYPE)
    if not assessment:
        raise FileNotFoundError(f"{ASSESSMENT_FILE} not indexed for {ARM_TYPE}")
    return assessment


def route_table_sync_property_paths() -> tuple[str, ...]:
    return sync_property_paths(load_route_table_assessment())


def route_table_arm_property_paths() -> tuple[str, ...]:
    return arm_property_paths(load_route_table_assessment())


def route_table_metrics_period_default() -> str:
    return metrics_period_default(load_route_table_assessment())


def route_table_monitor_metric_names() -> tuple[str, ...]:
    return monitor_metric_names(load_route_table_assessment())


def route_table_required_metric_keys() -> list[str]:
    return required_metric_keys(load_route_table_assessment())
