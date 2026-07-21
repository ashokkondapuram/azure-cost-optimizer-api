"""Tests for cosmosdb-assessment.json driven inventory, metrics, and cost fetch specs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COSMOS_ASSESSMENT = ROOT / "data" / "cosmosdb-assessment.json"


@pytest.fixture(scope="module")
def cosmos_assessment() -> dict:
    return json.loads(COSMOS_ASSESSMENT.read_text(encoding="utf-8"))


def test_cosmos_assessment_v2_schema(cosmos_assessment):
    assert cosmos_assessment["schema_version"] == "2.0"
    assert cosmos_assessment["resource_type"] == "database/cosmosdb"
    assert len(cosmos_assessment["rules"]) == 15
    assert len(cosmos_assessment["cases"]) >= 8


def test_cosmos_sync_property_paths_from_assessment(cosmos_assessment):
    from app.assessment.cosmosdb_fetch_spec import cosmos_sync_property_paths

    expected = tuple(cosmos_assessment["azure_properties"]["sync_property_paths"])
    assert cosmos_sync_property_paths() == expected
    assert "capabilities" in cosmos_sync_property_paths()


def test_cosmos_monitor_metrics_from_assessment(cosmos_assessment):
    from app.assessment.cosmosdb_fetch_spec import cosmos_monitor_metric_names, cosmos_monitor_metrics

    assessment_metrics = cosmos_assessment["azure_metrics"]["metrics"]
    profile_metrics = cosmos_monitor_metrics()
    assert len(profile_metrics) == len(assessment_metrics) == 10

    names = cosmos_monitor_metric_names()
    assert "TotalRequestUnits" in names
    assert "NormalizedRUConsumption" in names

    fact_keys = {m.fact_key for m in profile_metrics}
    assert "normalized_ru_pct" in fact_keys
    assert "total_ru" in fact_keys


def test_cosmos_cost_fields_from_assessment(cosmos_assessment):
    from app.assessment.cosmosdb_fetch_spec import (
        billed_mtd_normalized_key,
        cost_field_mapping,
        cosmos_cost_field_names,
    )

    assert len(cosmos_cost_field_names()) == 6
    mapping = cost_field_mapping()
    assert mapping["billed_mtd"] == "monthly_cost_usd"
    assert billed_mtd_normalized_key() == "monthly_cost_usd"


def test_resource_profile_uses_cosmos_assessment(cosmos_assessment):
    from app.resources.registry import (
        RESOURCE_MONITOR_PROFILES,
        TECHNICAL_FETCH_SPECS,
        assessment_driven_fetch_spec,
        assessment_driven_monitor_profile,
    )

    spec = TECHNICAL_FETCH_SPECS["database/cosmosdb"]
    assert spec.sync_property_paths == tuple(cosmos_assessment["azure_properties"]["sync_property_paths"])

    profile = RESOURCE_MONITOR_PROFILES["microsoft.documentdb/databaseaccounts"]
    assessment_names = [m["metric_name"] for m in cosmos_assessment["azure_metrics"]["metrics"]]
    assert profile.metric_names() == tuple(assessment_names)

    assert assessment_driven_fetch_spec("database/cosmosdb") is spec
    driven_profile = assessment_driven_monitor_profile("database/cosmosdb")
    assert driven_profile is not None
    assert driven_profile.canonical_type == "database/cosmosdb"


def test_hydrate_cosmos_rules_from_assessment():
    from copy import deepcopy

    from app.optimizer.advanced_rules import ADVANCED_RULES
    from it_services.database_cosmosdb.assessment_bridge import hydrate_cosmos_rules, optimization_thresholds

    rules = {rid: deepcopy(rule) for rid, rule in ADVANCED_RULES.items()}
    hydrate_cosmos_rules(rules)
    thresholds = optimization_thresholds()
    assert rules["COSMOS_SERVERLESS"].cosmos_serverless_ru_threshold == thresholds["cosmos_serverless_ru_threshold"]
    assert rules["COSMOS_RU_RIGHT_SIZING_UNDER"].cosmos_ru_low_pct == thresholds["cosmos_ru_low_pct"]


def test_cosmos_rule_evidence_from_assessment():
    from app.rule_evidence_config import required_evidence_for_rule

    evidence = required_evidence_for_rule("COSMOS_SERVERLESS", "database/cosmosdb")
    assert len(evidence) == 1
    assert evidence[0]["signal"] == "total_ru_consumed"
