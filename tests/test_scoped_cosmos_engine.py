"""Scoped Cosmos DB analysis keeps indexed resources in the engine path."""

from __future__ import annotations

from app.optimizer.advanced_rules import ADVANCED_RULES
from app.optimizer.extended_engine import ExtendedOptimizationEngine


def _cosmos_account(name: str = "cosmos1") -> dict:
    return {
        "id": f"/subscriptions/s/resourceGroups/rg/providers/Microsoft.DocumentDB/databaseAccounts/{name}",
        "name": name,
        "type": "Microsoft.DocumentDB/databaseAccounts",
        "location": "canadacentral",
        "properties": {
            "databaseAccountOfferType": "Standard",
            "capabilities": [],
            "consistencyPolicy": {"defaultConsistencyLevel": "Session"},
            "enableAutomaticFailover": False,
            "enableMultipleWriteLocations": False,
            "enableFreeTier": False,
            "locations": [{"locationName": "canadacentral", "failoverPriority": 0}],
        },
        "tags": {},
    }


def test_extended_engine_scoped_cosmos_produces_findings_when_sub_engines_disabled(monkeypatch):
    monkeypatch.setenv("ASSESSMENT_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("LEGACY_SUB_ENGINES_ENABLED", "false")

    engine = ExtendedOptimizationEngine()
    assert ADVANCED_RULES["COSMOS_PROVISIONED_EXTENDED"].enabled

    result = engine.analyze(
        subscription_id="93ca908b-0000-0000-0000-000000000001",
        cosmosdb=[_cosmos_account()],
        scoped_canonical_types=["database/cosmosdb"],
    )

    rule_ids = {f["rule_id"] for f in result.get("findings") or []}
    assert result["summary"]["total_findings"] > 0
    assert "COSMOS_PROVISIONED_EXTENDED" in rule_ids
