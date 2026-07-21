"""Tests for Azure Monitor time-series extraction and utilization fallback."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.monitor_metrics import (
    build_metrics_detail,
    metric_timeseries_from_payload,
    monitor_interval_for_timespan,
)
from app.resources import get_monitor_profile
from app.utilization_history import utilization_series_with_monitor_fallback


COSMOS_RID = (
    "/subscriptions/s/resourceGroups/rg/providers/Microsoft.DocumentDB/databaseAccounts/cosmos1"
)
VM_RID = "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
DISK_RID = "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/disks/d1"
AKS_RID = (
    "/subscriptions/s/resourceGroups/rg/providers/Microsoft.ContainerService/managedClusters/aks1"
)


def _payload_with_timestamps(metric_name: str, points: list[tuple[str, float]], agg: str = "average") -> dict:
    return {
        "value": [{
            "name": {"value": metric_name},
            "timeseries": [{
                "data": [
                    {"timeStamp": ts, agg: val}
                    for ts, val in points
                ],
            }],
        }],
    }


def test_metric_timeseries_from_payload_buckets_hourly_to_daily():
    payload = _payload_with_timestamps(
        "NormalizedRUConsumption",
        [
            ("2026-07-08T10:00:00Z", 10.0),
            ("2026-07-08T14:00:00Z", 20.0),
            ("2026-07-09T10:00:00Z", 30.0),
        ],
    )
    points = metric_timeseries_from_payload(
        payload,
        "NormalizedRUConsumption",
        aggregation="Average",
        bucket="day",
    )
    assert points == [
        {"date": "2026-07-08", "value": 15.0},
        {"date": "2026-07-09", "value": 30.0},
    ]


def test_build_metrics_detail_includes_series_points():
    profile = get_monitor_profile(COSMOS_RID, "database/cosmosdb")
    payload = _payload_with_timestamps(
        "NormalizedRUConsumption",
        [
            ("2026-07-08T10:00:00Z", 0.1),
            ("2026-07-09T10:00:00Z", 0.2),
        ],
    )
    detail = build_metrics_detail(payload, profile)
    ru_row = next(row for row in detail if row["fact_key"] == "normalized_ru_pct")
    assert len(ru_row["series_points"]) == 2
    assert ru_row["series_points"][0]["date"] == "2026-07-08"


def test_build_metrics_detail_keeps_average_series_when_only_max_stats_present():
    """Azure may return max-only points in one series and average in another."""
    profile = get_monitor_profile(COSMOS_RID, "database/cosmosdb")
    payload = {
        "value": [
            {
                "name": {"value": "NormalizedRUConsumption"},
                "timeseries": [{
                    "data": [
                        {"timeStamp": "2026-07-08T10:00:00Z", "maximum": 72.0},
                        {"timeStamp": "2026-07-09T10:00:00Z", "maximum": 80.0},
                    ],
                }],
            },
            {
                "name": {"value": "NormalizedRUConsumption"},
                "timeseries": [{
                    "data": [
                        {"timeStamp": "2026-07-08T10:00:00Z", "average": 18.0},
                        {"timeStamp": "2026-07-09T10:00:00Z", "average": 22.0},
                    ],
                }],
            },
        ],
    }
    detail = build_metrics_detail(payload, profile)
    ru_row = next(row for row in detail if row["fact_key"] == "normalized_ru_pct")
    assert len(ru_row["series_points"]) == 2
    assert ru_row["series_points"][0]["value"] == 18.0
    assert ru_row["stats"]["maximum"] == 80.0


def test_metric_value_from_monitor_payload_prefers_requested_aggregation():
    from app.monitor_metrics import metric_value_from_monitor_payload

    payload = {
        "value": [
            {
                "name": {"value": "NormalizedRUConsumption"},
                "timeseries": [{"data": [{"average": 18.0, "maximum": 72.0}]}],
            },
        ],
    }
    assert metric_value_from_monitor_payload(payload, "NormalizedRUConsumption", aggregation="Average") == 18.0
    assert metric_value_from_monitor_payload(payload, "NormalizedRUConsumption", aggregation="Maximum") == 72.0


@pytest.mark.parametrize(
    ("timespan", "expected"),
    [
        ("P1D", "PT1H"),
        ("P7D", "PT1H"),
        ("P30D", "PT6H"),
        ("P90D", "P1D"),
    ],
)
def test_monitor_interval_for_timespan(timespan, expected):
    assert monitor_interval_for_timespan(timespan) == expected


@pytest.mark.parametrize(
    ("resource_id", "canonical_type", "metric_name", "fact_key", "points", "agg"),
    [
        (
            VM_RID,
            "compute/vm",
            "Percentage CPU",
            "avg_cpu_pct",
            [("2026-07-08T10:00:00Z", 12.0), ("2026-07-09T10:00:00Z", 18.0)],
            "average",
        ),
        (
            DISK_RID,
            "compute/disk",
            "Composite Disk Read Operations/sec",
            "disk_read_iops",
            [("2026-07-08T10:00:00Z", 100.0), ("2026-07-09T10:00:00Z", 120.0)],
            "average",
        ),
        (
            AKS_RID,
            "containers/aks",
            "node_cpu_usage_percentage",
            "cluster_cpu_pct",
            [("2026-07-08T10:00:00Z", 35.0), ("2026-07-09T10:00:00Z", 42.0)],
            "maximum",
        ),
    ],
)
def test_build_metrics_detail_includes_series_points_for_all_resource_types(
    resource_id,
    canonical_type,
    metric_name,
    fact_key,
    points,
    agg,
):
    profile = get_monitor_profile(resource_id, canonical_type)
    payload = _payload_with_timestamps(metric_name, points, agg=agg)
    detail = build_metrics_detail(payload, profile)
    row = next(item for item in detail if item["fact_key"] == fact_key)
    assert len(row["series_points"]) == 2
    assert row["series_points"][0]["date"] == "2026-07-08"


def test_utilization_series_with_monitor_fallback_uses_monitor_when_history_sparse():
    class _FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return []

    fake_db = type("DB", (), {"query": lambda self, model: _FakeQuery()})()

    monitor_points = [
        {"date": "2026-07-08", "value": 0.15},
        {"date": "2026-07-09", "value": 0.2},
    ]
    with patch(
        "app.monitor_metrics.fetch_monitor_fact_timeseries",
        return_value=monitor_points,
    ):
        points, source = utilization_series_with_monitor_fallback(
            fake_db,
            COSMOS_RID,
            "normalized_ru_pct",
            subscription_id="s",
            timespan="P7D",
        )
    assert source == "monitor"
    assert points == monitor_points
