"""Tests for shared finding deduplication keys."""
from __future__ import annotations

from app.finding_dedupe import (
    dedupe_finding_dicts,
    open_finding_identity_key,
)


def test_identity_key_normalizes_trailing_slash():
    rid = "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Network/applicationGateways/agw1"
    key_a = open_finding_identity_key("sub-a", rid, "COST_HIGH_SPEND_REVIEW")
    key_b = open_finding_identity_key("sub-a", f"{rid}/", "COST_HIGH_SPEND_REVIEW")
    assert key_a == key_b


def test_subscription_commitment_rules_share_identity():
    key_a = open_finding_identity_key(
        "sub-a",
        "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        "SAVINGS_PLAN_OPPORTUNITY",
    )
    key_b = open_finding_identity_key(
        "sub-a",
        "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm2",
        "SAVINGS_PLAN_OPPORTUNITY_EXTENDED",
    )
    assert key_a == key_b


def test_dedupe_finding_dicts_keeps_latest():
    rid = "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Network/applicationGateways/agw1"
    findings = [
        {
            "subscription_id": "sub-a",
            "resource_id": rid,
            "rule_id": "COST_HIGH_SPEND_REVIEW",
            "detected_at": "2026-01-01T00:00:00Z",
            "estimated_savings_usd": 100,
        },
        {
            "subscription_id": "sub-a",
            "resource_id": f"{rid}/",
            "rule_id": "COST_HIGH_SPEND_REVIEW",
            "detected_at": "2026-02-01T00:00:00Z",
            "estimated_savings_usd": 200,
        },
    ]
    out = dedupe_finding_dicts(findings)
    assert len(out) == 1
    assert out[0]["estimated_savings_usd"] == 200
