"""Tests for Cosmos DB optimization engine."""

from __future__ import annotations

from app.optimizer.advanced_rules import ADVANCED_RULES
from app.optimizer.resource_engines.database.cosmos.analysis import analyze_cosmos
from app.optimizer.resource_engines.database.cosmos.optimization_rules import (
    evaluate_cosmos_api_cost_variance,
    evaluate_cosmos_autoscale_extended,
    evaluate_cosmos_hot_container,
    evaluate_cosmos_indexing_overprovisioned,
    evaluate_cosmos_ru_rightsizing_over,
    evaluate_cosmos_ru_rightsizing_under,
    evaluate_cosmos_serverless,
    evaluate_cosmos_throttling,
)
from app.cosmosdb_catalog import load_cosmosdb_pricing_models, parse_cosmos_arm_account


class _FakeEngine:
    def __init__(self):
        self.rules = ADVANCED_RULES

    def _extract_rg(self, rid: str) -> str:
        parts = (rid or "").split("/")
        if "resourceGroups" in parts:
            idx = parts.index("resourceGroups")
            return parts[idx + 1] if idx + 1 < len(parts) else ""
        return ""

    def _finding(self, **kwargs):
        from datetime import datetime, timezone
        from app.optimizer.core.finding import ExtendedFinding

        rule = kwargs.pop("rule")
        resource = kwargs.get("resource") or {}
        rid = resource.get("id") or ""
        savings = float(kwargs.get("savings", 0) or 0)
        return ExtendedFinding(
            rule_id=rule.id,
            rule_name=rule.name,
            category=rule.category.value,
            severity=rule.severity.value,
            subscription_id=kwargs.get("subscription_id", ""),
            resource_id=rid,
            resource_name=resource.get("name") or "",
            resource_type=resource.get("type") or "database/cosmosdb",
            resource_group=self._extract_rg(rid),
            location=resource.get("location") or "",
            detail=kwargs.get("detail", ""),
            recommendation=kwargs.get("recommendation", ""),
            estimated_savings_usd=round(savings, 2),
            annualized_savings_usd=round(savings * 12, 2),
            waste_score=kwargs.get("waste_score", 0),
            confidence_score=kwargs.get("confidence", 0),
            action_priority=kwargs.get("priority", "P3"),
            impact=kwargs.get("impact", ""),
            evidence=kwargs.get("evidence") or {},
            tags=resource.get("tags") or {},
            detected_at=datetime.now(timezone.utc).isoformat(),
        )


def _account(
    *,
    name: str = "cosmos1",
    kind: str = "GlobalDocumentDB",
    capabilities: list | None = None,
    facts: dict | None = None,
    tags: dict | None = None,
    consistency: str = "Session",
    locations: list | None = None,
) -> dict:
    props = {
        "databaseAccountOfferType": "Standard",
        "capabilities": capabilities or [],
        "consistencyPolicy": {"defaultConsistencyLevel": consistency},
        "enableAutomaticFailover": False,
        "enableMultipleWriteLocations": False,
        "enableFreeTier": False,
        "locations": locations or [{"locationName": "canadacentral", "failoverPriority": 0}],
    }
    row = {
        "id": f"/subscriptions/s/resourceGroups/rg/providers/Microsoft.DocumentDB/databaseAccounts/{name}",
        "name": name,
        "kind": kind,
        "location": "canadacentral",
        "properties": props,
        "tags": tags or {},
    }
    if facts:
        row["_technical_facts"] = {**facts, "data_source": "azure_monitor"}
    return row


def test_cosmos_pricing_models_loads():
    specs = load_cosmosdb_pricing_models()
    assert specs.get("schema_version") == 1
    assert "provisioned_manual" in specs.get("pricing_models", {})
    assert "Sql" in specs.get("api_types", {})


def test_parse_cosmos_arm_account_sql():
    ctx = parse_cosmos_arm_account(_account(kind="GlobalDocumentDB"))
    assert ctx["api_type"] == "Sql"
    assert ctx["serverless_enabled"] is False


def test_parse_cosmos_arm_account_mongodb():
    ctx = parse_cosmos_arm_account(_account(kind="MongoDB"))
    assert ctx["api_type"] == "MongoDB"
    assert ctx["api_ru_multiplier"] > 1.0


def test_serverless_candidate_low_ru():
    acct = _account(facts={"total_ru": 12000.0, "request_count": 5000.0})
    ctx = parse_cosmos_arm_account(acct)
    draft = evaluate_cosmos_serverless(acct, ctx, 180.0, ADVANCED_RULES["COSMOS_SERVERLESS"])
    assert draft is not None
    assert draft.rule_id == "COSMOS_SERVERLESS"


def test_ru_rightsizing_under():
    acct = _account(facts={"normalized_ru_pct": 12.0, "provisioned_throughput": 4000.0})
    ctx = parse_cosmos_arm_account(acct)
    draft = evaluate_cosmos_ru_rightsizing_under(acct, ctx, 250.0, ADVANCED_RULES["COSMOS_RU_RIGHT_SIZING_UNDER"])
    assert draft is not None
    assert draft.rule_id == "COSMOS_RU_RIGHT_SIZING_UNDER"


def test_ru_rightsizing_over():
    acct = _account(facts={"normalized_ru_pct": 88.0})
    ctx = parse_cosmos_arm_account(acct)
    draft = evaluate_cosmos_ru_rightsizing_over(acct, ctx, 300.0, ADVANCED_RULES["COSMOS_RU_RIGHT_SIZING_OVER"])
    assert draft is not None
    assert draft.savings == 0.0


def test_throttling_detected():
    acct = _account(facts={"normalized_ru_peak_pct": 98.0, "normalized_ru_pct": 92.0})
    ctx = parse_cosmos_arm_account(acct)
    draft = evaluate_cosmos_throttling(acct, ctx, 300.0, ADVANCED_RULES["COSMOS_THROTTLING_DETECTED"])
    assert draft is not None
    assert draft.priority == "P1"


def test_hot_container_skew():
    acct = _account(facts={"normalized_ru_pct": 30.0, "normalized_ru_peak_pct": 90.0, "ru_skew_ratio": 3.0})
    ctx = parse_cosmos_arm_account(acct)
    draft = evaluate_cosmos_hot_container(acct, ctx, 200.0, ADVANCED_RULES["COSMOS_HOT_CONTAINER_DETECTED"])
    assert draft is not None
    assert draft.rule_id == "COSMOS_HOT_CONTAINER_DETECTED"


def test_api_cost_variance_mongodb():
    acct = _account(kind="MongoDB")
    ctx = parse_cosmos_arm_account(acct)
    draft = evaluate_cosmos_api_cost_variance(acct, ctx, 150.0, ADVANCED_RULES["COSMOS_API_COST_VARIANCE"])
    assert draft is not None
    assert "MongoDB" in draft.detail


def test_indexing_overprovisioned():
    acct = _account(facts={"data_usage_bytes": 100.0, "index_usage_bytes": 200.0, "index_to_data_ratio": 2.0})
    ctx = parse_cosmos_arm_account(acct)
    draft = evaluate_cosmos_indexing_overprovisioned(acct, ctx, 120.0, ADVANCED_RULES["COSMOS_INDEXING_OVERPROVISIONED"])
    assert draft is not None


def test_autoscale_extended_low_utilization():
    acct = _account(facts={"normalized_ru_pct": 15.0, "request_count": 1000.0, "total_ru": 8000.0})
    ctx = parse_cosmos_arm_account(acct)
    draft = evaluate_cosmos_autoscale_extended(acct, ctx, 200.0, ADVANCED_RULES["COSMOS_AUTOSCALE_EXTENDED"])
    assert draft is not None


def test_analyze_cosmos_integration():
    engine = _FakeEngine()
    accounts = [
        _account(facts={"total_ru": 5000.0, "request_count": 1000.0}),
        _account(kind="MongoDB"),
        _account(facts={"normalized_ru_pct": 90.0}),
    ]
    costs = {a["id"].lower(): 100.0 for a in accounts}
    findings = analyze_cosmos(engine, "sub", accounts, costs)
    rule_ids = {f.rule_id for f in findings}
    assert "COSMOS_PROVISIONED_EXTENDED" in rule_ids
    assert "COSMOS_SERVERLESS" in rule_ids
    assert "COSMOS_API_COST_VARIANCE" in rule_ids
    assert "COSMOS_RU_RIGHT_SIZING_OVER" in rule_ids
