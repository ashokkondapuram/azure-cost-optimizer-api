"""Tests for assessment metric baseline enrichment and no-baseline fallbacks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.assessment.catalog import get_assessment_for_arm_type
from app.assessment.metric_enrichment import enrich_assessment_metric_stats
from app.assessment.normalizer import build_normalized_record
from app.assessment.runtime import evaluate_assessment_rules
from app.finding_quality import is_action_centre_finding


ROOT = Path(__file__).resolve().parents[1]
AKS_ASSESSMENT = json.loads((ROOT / "data" / "aks-assessment.json").read_text(encoding="utf-8"))


def test_static_baseline_when_no_historical_series():
    assessment = get_assessment_for_arm_type("Microsoft.ContainerService/managedClusters")
    enriched = enrich_assessment_metric_stats(
        {"cluster_mem_pct": 62.5},
        flat_metrics={"cluster_mem_pct": 62.5},
        assessment=assessment,
        canonical_type="containers/aks",
    )
    node = enriched.get("node_memory_working_set_percentage") or {}
    assert node.get("baselineAvailable") is True
    assert node.get("baselineSource") == "static_threshold"
    assert node.get("avg") == pytest.approx(62.5)
    assert node.get("p95LimitPct") == pytest.approx(62.5)


def test_historical_baseline_when_enough_days():
    assessment = get_assessment_for_arm_type("Microsoft.ContainerService/managedClusters")
    series = [40.0, 42.0, 41.0, 43.0, 44.0, 80.0, 82.0]
    payload = {
        "metrics": [
            {
                "metric_name": "node_memory_working_set_percentage",
                "series_points": [{"date": f"2026-07-{10 + i:02d}", "value": v} for i, v in enumerate(series)],
            }
        ]
    }
    enriched = enrich_assessment_metric_stats(
        {"cluster_mem_pct": 82.0},
        flat_metrics={"cluster_mem_pct": 82.0},
        assessment=assessment,
        canonical_type="containers/aks",
        metrics_payload=payload,
    )
    node = enriched["node_memory_working_set_percentage"]
    assert node["baselineAvailable"] is True
    assert node["baselineSource"] == "historical"
    assert node["baselineDays"] >= 5
    assert node.get("trendPct") is not None


def test_baseline_missing_rule_not_applicable_without_metric_field():
    rule = next(
        r for r in (AKS_ASSESSMENT.get("bestOptimizationRules") or [])
        if r.get("id") == "best_metric_node_memory_working_set_percentage_baseline_missing"
    )
    resource = {
        "resource_type": "Microsoft.ContainerService/managedClusters",
        "metrics": {},
    }
    matched = evaluate_assessment_rules(
        AKS_ASSESSMENT,
        resource,
        include_best_optimization_rules=True,
    )
    assert rule["id"] not in {r.get("id") for r in matched}


def test_baseline_missing_rule_skipped_when_baseline_available():
    assessment = get_assessment_for_arm_type("Microsoft.ContainerService/managedClusters")
    record = build_normalized_record(
        {
            "subscription_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "resource_id": "/subscriptions/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/resourceGroups/rg/providers/Microsoft.ContainerService/managedClusters/aks1",
            "resource_name": "aks1",
            "resource_type": "Microsoft.ContainerService/managedClusters",
            "canonical_type": "containers/aks",
            "resource_group": "rg",
            "location": "eastus",
            "sku": "",
            "state": "Succeeded",
            "properties": {},
            "tags": {},
            "monthly_cost_usd": 100.0,
            "monthly_cost_billing": 100.0,
            "billing_currency": "USD",
        },
        metrics={"cluster_mem_pct": 55.0, "cluster_cpu_pct": 22.0},
        assessment=assessment,
    )
    matched = evaluate_assessment_rules(
        assessment,
        record,
        include_best_optimization_rules=True,
    )
    baseline_rules = [r for r in matched if "_baseline_missing" in str(r.get("id") or "")]
    assert baseline_rules == []


def test_baseline_missing_excluded_from_action_centre():
    finding = {
        "rule_id": "best_metric_node_memory_working_set_percentage_baseline_missing",
        "resource_id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.ContainerService/managedClusters/aks1",
        "resource_type": "containers/aks",
        "evidence": {"rule_source": "assessment_json"},
    }
    assert is_action_centre_finding(finding) is False


def test_exclude_metric_gaps_skips_baseline_missing_rules():
    assessment = {
        "recommendationRules": [
            {
                "id": "best_metric_node_memory_working_set_percentage_baseline_missing",
                "recommendationAction": "investigate",
                "condition": {
                    "type": "all",
                    "conditions": [
                        {
                            "field": "metrics.node_memory_working_set_percentage.baselineAvailable",
                            "operator": "neq",
                            "value": True,
                            "missingData": "rule_not_applicable",
                        }
                    ],
                },
            }
        ],
    }
    resource = {
        "metrics": {
            "node_memory_working_set_percentage": {"baselineAvailable": False},
        },
    }
    matched = evaluate_assessment_rules(assessment, resource, exclude_metric_gaps=True)
    assert matched == []
