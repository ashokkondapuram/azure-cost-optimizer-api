"""Tests for Azure Monitor stats extraction and VMSS instance metrics."""

import pytest

from app.monitor_metrics import (
    build_metrics_detail,
    metric_statistics_from_payload,
    parse_vmss_arm_id,
)
from app.resources import get_monitor_profile


VMSS_RID = (
    "/subscriptions/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    "/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachineScaleSets/myvmss"
)


def _sample_payload(metric_name: str, averages: list[float]) -> dict:
    return {
        "value": [{
            "name": {"value": metric_name},
            "timeseries": [{
                "data": [
                    {"average": avg, "minimum": avg * 0.8, "maximum": avg * 1.2}
                    for avg in averages
                ],
            }],
        }],
    }


def test_metric_statistics_from_payload_uses_azure_aggregations_only():
    payload = _sample_payload("Percentage CPU", [10.0, 20.0, 30.0, 40.0])
    stats = metric_statistics_from_payload(payload, "Percentage CPU")
    assert stats["average"] == pytest.approx(25.0)
    assert stats["minimum"] == pytest.approx(8.0)
    assert stats["maximum"] == pytest.approx(48.0)
    assert "p50" not in stats
    assert "p95" not in stats


def test_build_metrics_detail_for_vmss_profile():
    profile = get_monitor_profile(VMSS_RID)
    assert profile is not None
    payload = _sample_payload("Percentage CPU", [5.0, 15.0, 25.0])
    detail = build_metrics_detail(payload, profile)
    cpu_row = next(row for row in detail if row["metric_name"] == "Percentage CPU")
    assert cpu_row["stats"]["average"] == pytest.approx(15.0)
    assert cpu_row["display_stats"] == ["average"]
    assert set(cpu_row["stats"]) == {"average"}
    assert "minimum" not in cpu_row["stats"]


def test_parse_vmss_arm_id():
    parsed = parse_vmss_arm_id(VMSS_RID)
    assert parsed == (
        "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "rg-prod",
        "myvmss",
    )
    assert parse_vmss_arm_id("/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1") is None
