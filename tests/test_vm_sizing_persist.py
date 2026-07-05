"""Tests for persisting live VM sizing as open optimization findings."""
from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, OptimizationFinding
from app.cost_utils import normalize_monthly_cost_usd, resource_cost_usd_from_map
from app.vm_sizing_persist import build_vm_sizing_finding_dict, compute_vm_sizing_recommendation, upsert_vm_sizing_open_finding


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _vm(sku: str = "Standard_D2ads_v6") -> dict:
    return {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        "name": "vm1",
        "type": "Microsoft.Compute/virtualMachines",
        "location": "eastus",
        "properties": {"hardwareProfile": {"vmSize": sku}},
    }


def _recommendation(action: str = "cross_family") -> dict:
    return {
        "action": action,
        "current_sku": "Standard_D2ads_v6",
        "suggested_sku": "Standard_B1ls",
        "current_family": "D",
        "suggested_family": "B",
        "family_label": "Burstable",
        "direction": "lateral",
        "avg_cpu_pct": 3.2,
        "avg_memory_pct": 12.0,
        "confidence": 66,
        "reasons": ["Workload shape may fit the Burstable family better."],
    }


def _utilization() -> dict:
    return {
        "avg_cpu_pct": 3.2,
        "avg_memory_pct": 12.0,
        "has_cpu": True,
        "has_memory": True,
        "metrics_window": "P7D",
    }


@patch("app.optimizer.resource_engines.compute.vm.helpers.estimate_vm_sku_savings")
def test_build_vm_sizing_finding_dict_cross_family(mock_retail):
    mock_retail.return_value = {
        "current_sku_monthly_usd": 120.0,
        "suggested_sku_monthly_usd": 32.0,
        "estimated_monthly_savings_usd": 88.0,
        "pricing_status": "available",
        "pricing_source": "azure_retail_prices",
    }
    finding = build_vm_sizing_finding_dict(
        subscription_id="sub",
        vm=_vm(),
        recommendation=_recommendation(),
        utilization=_utilization(),
        pricing=mock_retail.return_value,
        monthly_cost=100.0,
    )
    assert finding is not None
    assert finding["rule_id"] == "VM_RIGHTSIZE_FAMILY"
    assert finding["severity"] == "MEDIUM"
    assert finding["estimated_savings_usd"] == pytest.approx(88.0)
    assert finding["evidence"]["sizing_action"] == "cross_family"
    assert "Standard_B1ls" in finding["recommendation"]


@patch("app.optimizer.resource_engines.compute.vm.helpers.estimate_vm_sku_savings")
def test_upsert_vm_sizing_open_finding_creates_open_row(mock_retail, db_session):
    mock_retail.return_value = {
        "current_sku_monthly_usd": 120.0,
        "suggested_sku_monthly_usd": 32.0,
        "estimated_monthly_savings_usd": 88.0,
        "pricing_status": "available",
        "pricing_source": "azure_retail_prices",
    }
    vm = _vm()
    row = upsert_vm_sizing_open_finding(
        db_session,
        subscription_id="sub",
        vm=vm,
        recommendation=_recommendation(),
        utilization=_utilization(),
        pricing=mock_retail.return_value,
        monthly_cost=100.0,
    )
    assert row is not None
    assert row.status == "open"
    assert row.severity == "MEDIUM"
    assert row.rule_id == "VM_RIGHTSIZE_FAMILY"
    assert row.estimated_savings_usd == pytest.approx(88.0)

    stored = (
        db_session.query(OptimizationFinding)
        .filter(OptimizationFinding.id == row.id)
        .one()
    )
    evidence = json.loads(stored.evidence_json or "{}")
    assert evidence.get("sizing_action") == "cross_family"


@patch("app.optimizer.resource_engines.compute.vm.helpers.estimate_vm_sku_savings")
def test_upsert_vm_sizing_open_finding_updates_existing(mock_retail, db_session):
    mock_retail.return_value = {
        "current_sku_monthly_usd": 120.0,
        "suggested_sku_monthly_usd": 32.0,
        "estimated_monthly_savings_usd": 88.0,
        "pricing_status": "available",
    }
    vm = _vm()
    first = upsert_vm_sizing_open_finding(
        db_session,
        subscription_id="sub",
        vm=vm,
        recommendation=_recommendation(),
        utilization=_utilization(),
        pricing=mock_retail.return_value,
    )
    updated_rec = {**_recommendation(), "suggested_sku": "Standard_B2s"}
    mock_retail.return_value = {
        **mock_retail.return_value,
        "suggested_sku_monthly_usd": 48.0,
        "estimated_monthly_savings_usd": 72.0,
    }
    second = upsert_vm_sizing_open_finding(
        db_session,
        subscription_id="sub",
        vm=vm,
        recommendation=updated_rec,
        utilization=_utilization(),
        pricing=mock_retail.return_value,
    )
    assert second.id == first.id
    assert second.estimated_savings_usd == pytest.approx(72.0)
    assert "Standard_B2s" in (second.recommendation or "")


def test_resource_cost_usd_from_map_extracts_usd():
    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
    cost_map = {
        rid.lower(): {"pretax": 50.0, "usd": 45.5, "currency": "USD", "service_name": "Virtual Machines"},
    }
    assert resource_cost_usd_from_map(cost_map, rid) == pytest.approx(45.5)


@patch("app.vm_sizing_persist.recommend_vm_sku")
@patch("app.azure_retail_pricing.estimate_vm_sku_savings")
def test_compute_vm_sizing_recommendation_blends_export_cost(mock_retail, mock_recommend):
    from app.vm_sizing import VmSizingRecommendation

    mock_recommend.return_value = VmSizingRecommendation(
        action="downgrade",
        current_sku="Standard_D2ads_v6",
        suggested_sku="Standard_D2ads_v5",
        current_family="D",
        suggested_family="D",
        family_label="General purpose",
        direction="down",
        avg_cpu_pct=3.2,
        avg_memory_pct=12.0,
        confidence=70,
        reasons=["Low CPU"],
    )
    mock_retail.return_value = {
        "current_monthly_cost_usd": 120.0,
        "suggested_monthly_cost_usd": 32.0,
        "estimated_monthly_savings_usd": 88.0,
    }
    util, recommendation, pricing = compute_vm_sizing_recommendation(
        vm=_vm(),
        catalog=[{"name": "Standard_D2ads_v6", "numberOfCores": 2, "memoryInMB": 8192}],
        metrics={"cpu_avg_pct": 3.0, "memory_avg_pct": 10.0},
        monthly_cost=95.0,
    )
    assert recommendation is not None
    assert pricing is not None
    assert pricing["current_monthly_cost_usd"] == pytest.approx(95.0)


def test_normalize_monthly_cost_usd_accepts_cost_map_entry():
    entry = {"pretax": 100.0, "usd": 95.0, "currency": "USD"}
    assert normalize_monthly_cost_usd(entry) == pytest.approx(95.0)
