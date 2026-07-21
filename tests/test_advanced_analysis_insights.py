"""Tests for advanced analysis insight copy."""

from app.advanced_analysis_insights import build_advanced_insights


def test_insights_without_metrics_use_plain_language():
    result = build_advanced_insights(
        workload={
            "workload_type": "steady",
            "burstiness_score": 0,
            "peak_hour_factor": 1,
            "utilization_trend": "unknown",
        },
        dependencies={
            "blast_radius": 0,
            "max_criticality": "low",
            "sla_tier": "none",
            "direct_outbound": [],
            "direct_inbound": [],
            "transitive_dependent_count": 0,
        },
        trends={
            "cost_trajectory": "stable",
            "cost_vs_prev_month_pct": None,
            "monthly_cost_usd": 120.0,
            "insufficient_history": True,
        },
        utilization_evidence={"has_monitor_data": False},
    )

    assert "Limited telemetry" in result["headline"]
    assert result["workload"][1]["value"] == "No spike data"
    assert result["dependencies"][0]["value"] == "Isolated"
    assert result["cost"][0]["value"] == "Stable"


def test_insights_with_cpu_evidence():
    result = build_advanced_insights(
        workload={
            "workload_type": "bursty",
            "burstiness_score": 45,
            "peak_hour_factor": 2.4,
            "utilization_trend": "increasing",
        },
        dependencies={
            "blast_radius": 3,
            "max_criticality": "high",
            "sla_tier": "gold",
            "direct_outbound": ["a", "b"],
            "direct_inbound": ["c"],
            "transitive_dependent_count": 1,
        },
        trends={
            "cost_trajectory": "increasing",
            "cost_vs_prev_month_pct": 18.5,
            "monthly_cost_usd": 900,
            "insufficient_history": False,
        },
        utilization_evidence={
            "has_monitor_data": True,
            "avg_cpu_pct": 22.5,
            "max_cpu_pct": 54.0,
        },
    )

    assert any(item["label"] == "CPU evidence" for item in result["workload"])
    assert result["dependencies"][2]["value"] == "Gold"
    assert "Up 18.5%" in result["cost"][0]["value"]
