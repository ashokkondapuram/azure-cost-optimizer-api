"""Tests for region governance and pillar signal computation."""

from __future__ import annotations

from app.assessment.pillar_signals import compute_pillar_signals
from app.assessment.region_governance import (
    classify_region,
    compute_region_signals,
    is_region_approved,
    recommended_region,
)
from app.assessment.signals import compute_signals
from app.assessment.shared_config import load_pillar_triggers, load_region_governance_policy


def test_region_policy_loads():
    policy = load_region_governance_policy()
    assert policy["primary_approved_region"] == "canadacentral"
    assert "canadaeast" in policy["classifications"]["approved"]["regions"]


def test_pillar_triggers_load():
    triggers = load_pillar_triggers()
    assert "cost" in triggers["pillars"]
    assert "performance" in triggers["pillars"]
    assert "Microsoft.ServiceBus/namespaces" in triggers["service_overrides"]


def test_canadacentral_is_approved():
    assert is_region_approved("canadacentral") is True
    assert classify_region("canadacentral") == "approved"


def test_eastus_is_unclassified():
    assert is_region_approved("eastus") is False
    assert classify_region("eastus") == "unclassified"


def test_recommended_region_for_service_bus():
    region = recommended_region(
        "eastus",
        resource_type="Microsoft.ServiceBus/namespaces",
        is_production=True,
    )
    assert region == "canadacentral"


def test_region_signals_for_unapproved_resource():
    record = {
        "location": "eastus",
        "resource_type": "Microsoft.ServiceBus/namespaces",
        "resource": {"location": "eastus", "type": "Microsoft.ServiceBus/namespaces"},
        "tags": {"Environment": "production"},
    }
    signals = compute_region_signals(record)
    assert signals["regionApproved"] is False
    assert signals["recommendedRegion"] == "canadacentral"
    assert signals["regionMoveAllowed"] is False
    assert signals["regionMigrationRequired"] is True


def test_service_bus_pillar_signals_throttling():
    record = {
        "resource_type": "Microsoft.ServiceBus/namespaces",
        "resource": {"sku": "Premium", "type": "Microsoft.ServiceBus/namespaces"},
        "metrics": {"servererrors": 5, "incoming_messages": 100},
        "cost": {"monthlyActualCost": 286},
        "properties": {},
        "tags": {},
        "policy": {},
    }
    signals = compute_pillar_signals(record)
    assert signals["throttledOrServerErrors"] is True
    assert signals["monthlyActualCost"] == 286


def test_service_bus_premium_underutilized():
    record = {
        "resource_type": "Microsoft.ServiceBus/namespaces",
        "resource": {"sku": "Premium"},
        "metrics": {"avg_cpu_pct": 10, "avg_memory_pct": 15, "incoming_messages": 50},
        "cost": {"monthlyActualCost": 286},
        "properties": {},
        "tags": {},
        "policy": {},
    }
    signals = compute_signals(record)
    assert signals["premiumUnderutilized"] is True
    assert signals["regionApproved"] is False
