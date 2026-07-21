"""Tests for Cosmos DB primary recommendation selection."""

from __future__ import annotations

from app.optimizer.core.finding import ExtendedFinding
from it_services.database_cosmosdb.engine.primary_recommendation import (
    consolidate_cosmos_findings,
    pick_primary_cosmos_finding,
    select_primary_cosmos_findings,
)


def _finding(rule_id: str, *, savings: float = 0, severity: str = "MEDIUM") -> ExtendedFinding:
    return ExtendedFinding(
        rule_id=rule_id,
        rule_name=rule_id,
        category="cost",
        severity=severity,
        resource_id="/subscriptions/s/resourceGroups/rg/providers/Microsoft.DocumentDB/databaseAccounts/acct1",
        resource_name="acct1",
        resource_type="database/cosmosdb",
        subscription_id="s",
        resource_group="rg",
        location="eastus",
        detail="detail",
        recommendation="recommendation",
        estimated_savings_usd=savings,
        annualized_savings_usd=savings * 12,
        waste_score=50,
        confidence_score=70,
        action_priority="P2",
        impact="cost",
        evidence={},
        tags={},
        detected_at="2026-07-11T00:00:00Z",
    )


def test_hot_partition_beats_serverless_downsize():
    findings = [
        _finding("COSMOS_SERVERLESS", savings=200),
        _finding("COSMOS_HOT_CONTAINER_DETECTED", savings=50, severity="HIGH"),
    ]
    winner = pick_primary_cosmos_finding(findings)
    assert winner is not None
    assert winner.rule_id == "COSMOS_HOT_CONTAINER_DETECTED"


def test_throttling_suppresses_serverless():
    findings = [
        _finding("COSMOS_SERVERLESS", savings=300),
        _finding("COSMOS_THROTTLING_DETECTED", savings=0, severity="HIGH"),
    ]
    winner = pick_primary_cosmos_finding(findings)
    assert winner.rule_id == "COSMOS_THROTTLING_DETECTED"


def test_one_primary_per_account():
    findings = [
        _finding("COSMOS_SERVERLESS", savings=100),
        _finding("COSMOS_INDEXING_OVERPROVISIONED", savings=40, severity="LOW"),
        _finding(
            "COSMOS_AUTOSCALE_EXTENDED",
            savings=80,
            severity="MEDIUM",
        ),
    ]
    # Same resource — should collapse to one
    primary = select_primary_cosmos_findings(findings)
    assert len(primary) == 1


def test_consolidate_marks_primary_and_what_if():
    findings = [_finding("COSMOS_SERVERLESS", savings=120)]
    out = consolidate_cosmos_findings(findings)
    assert len(out) == 1
    assert out[0].evidence.get("primary_recommendation") is True
