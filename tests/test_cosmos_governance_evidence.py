"""Governance region rules and evidence metadata filtering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COSMOS_ASSESSMENT = ROOT / "data" / "cosmosdb-assessment.json"


def test_cosmos_assessment_has_no_region_governance_rules():
    data = json.loads(COSMOS_ASSESSMENT.read_text(encoding="utf-8"))
    rule_ids = {str(r.get("rule_id") or "").lower() for r in data.get("rules") or []}
    assert "best_unapproved_region" not in rule_ids
    assert not any("unapproved_region" in rid for rid in rule_ids)
    for case in data.get("cases") or []:
        rid = str(case.get("rule_id") or "").lower()
        assert "unapproved_region" not in rid


def test_v2_cosmos_skips_legacy_assessment_json_findings():
    from app.assessment.catalog import get_assessment_for_arm_type
    from app.optimizer.platform.runtime.base import ResourceSubEngine
    from it_services.database_cosmosdb.engine.sub_engine import CosmosSubEngine

    assessment = get_assessment_for_arm_type("Microsoft.DocumentDB/databaseAccounts")
    assert assessment is not None
    assert str(assessment.get("schema_version") or "").startswith("2")

    class _StubEngine:
        rules = {}

    class _StubCtx:
        subscription_id = "sub"
        cost_by_resource = {}
        global_config = {}

        def metrics_for_resource(self, *_args, **_kwargs):
            return {}

        def facts_for_resource(self, *_args, **_kwargs):
            return {}

        def advisor_for_resource(self, *_args, **_kwargs):
            return []

    sub = CosmosSubEngine(_StubEngine(), _StubCtx())  # type: ignore[arg-type]
    resource = {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.DocumentDB/databaseAccounts/acct1",
        "name": "acct1",
        "type": "Microsoft.DocumentDB/databaseAccounts",
        "location": "westus",
        "properties": {"databaseAccountOfferType": "Standard"},
    }
    prepared = sub.prepare_resources([resource])
    findings = sub.evaluate_assessment_findings(prepared)
    assert findings == []


def test_region_governance_rule_blocked_unless_enabled():
    from app.assessment.governance_filter import is_region_governance_rule, region_governance_enabled
    from app.assessment.runtime import evaluate_assessment_rules

    rule = {
        "id": "best_unapproved_region",
        "pillar": "governance",
        "recommendationAction": "migrate_region",
        "condition": {
            "type": "all",
            "conditions": [{"field": "signals.regionApproved", "operator": "is_false", "value": True}],
        },
    }
    assessment = {
        "resourceType": "Microsoft.DocumentDB/databaseAccounts",
        "recommendationRules": [rule],
    }
    record = {
        "resource_type": "Microsoft.DocumentDB/databaseAccounts",
        "location": "westus",
        "signals": {"regionApproved": False},
    }
    assert is_region_governance_rule(rule)
    assert not region_governance_enabled(assessment)
    matched = evaluate_assessment_rules(assessment, record)
    assert matched == []


def test_sanitize_evidence_strips_governance_metadata():
    from app.finding_evidence import enrich_finding_for_api, sanitize_evidence_for_api

    raw = {
        "engine": "assessment_json",
        "rule_source": "assessment_json",
        "sub_engine": "database/cosmosdb",
        "recommendation_action": "migrate_region",
        "pillar": "governance",
        "offer_type": "Standard",
        "region_count": 2,
        "normalized_ru_pct": 42.5,
        "evidence_rows": [
            {
                "signal": "ru_utilization_pct",
                "label": "RU utilization",
                "value": "42.5%",
                "threshold": "< 20%",
                "status": "warn",
            }
        ],
    }
    cleaned = sanitize_evidence_for_api(raw)
    for key in (
        "engine",
        "rule_source",
        "sub_engine",
        "recommendation_action",
        "pillar",
        "offer_type",
        "region_count",
    ):
        assert key not in cleaned
    assert cleaned["normalized_ru_pct"] == 42.5
    assert len(cleaned["evidence_rows"]) == 1

    finding = enrich_finding_for_api(
        {
            "rule_id": "COSMOS_RU_RIGHT_SIZING_UNDER",
            "resource_id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.DocumentDB/databaseAccounts/acct1",
            "evidence": raw,
        }
    )
    ev = finding["evidence"]
    assert "engine" not in ev
    assert "offer_type" not in ev


def test_region_governance_finding_filtered_from_action_centre():
    from app.finding_quality import is_action_centre_finding, is_valuable_finding

    finding = {
        "rule_id": "best_unapproved_region",
        "category": "governance",
        "severity": "MEDIUM",
        "resource_id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.DocumentDB/databaseAccounts/acct1",
        "resource_type": "database/cosmosdb",
        "estimated_savings_usd": 0,
        "confidence_score": 60,
        "evidence": {
            "engine": "assessment_json",
            "recommendation_action": "migrate_region",
            "pillar": "governance",
        },
    }
    assert not is_action_centre_finding(finding)
    assert not is_valuable_finding(finding)
