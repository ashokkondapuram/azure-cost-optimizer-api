"""Tests for governance filters on cost-driving signal payloads."""

from app.cost_signals_filters import (
    filter_cost_drivers,
    filter_cost_driving_metrics,
    filter_metrics_payload_for_cost_signals,
    is_governance_cost_signal,
)


def test_is_governance_cost_signal_region_approval():
    assert is_governance_cost_signal({"label": "Region approval", "fact_key": "regionApproved"})
    assert is_governance_cost_signal({"label": "Approve region"})
    assert is_governance_cost_signal({"kind": "region", "label": "Recommended region"})
    assert is_governance_cost_signal({"rules": ["best_unapproved_region"]})


def test_is_governance_cost_signal_keeps_utilization_metrics():
    assert not is_governance_cost_signal({"fact_key": "avg_cpu_pct", "label": "Average CPU utilization"})
    assert not is_governance_cost_signal({"fact_key": "region_count", "label": "Region count"})


def test_filter_metrics_payload_for_cost_signals():
    payload = {
        "metrics": [
            {"fact_key": "avg_cpu_pct", "label": "Average CPU", "trigger": {}},
            {"fact_key": "regionApproved", "label": "Region approval", "trigger": {}},
        ],
        "derived": [],
        "cost_driver_mapping": {
            "cost_drivers": [
                {"kind": "metric", "fact_key": "avg_cpu_pct", "label": "Average CPU"},
                {"kind": "region", "fact_key": "region_classification", "label": "Region approval"},
            ],
        },
    }

    filtered = filter_metrics_payload_for_cost_signals(payload)
    assert len(filtered["metrics"]) == 1
    assert filtered["metrics"][0]["fact_key"] == "avg_cpu_pct"
    assert len(filtered["cost_driver_mapping"]["cost_drivers"]) == 1
    assert filter_cost_driving_metrics(payload["metrics"])[0]["fact_key"] == "avg_cpu_pct"
    assert len(filter_cost_drivers(payload["cost_driver_mapping"]["cost_drivers"])) == 1
