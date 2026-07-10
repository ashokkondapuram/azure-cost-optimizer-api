"""Tests for unified VM cost decision layer."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.advisor_vm_targets import AdvisorVmTarget
from app.vm_cost_decision import resolve_vm_cost_decision
from app.vm_sizing import VmSizingRecommendation


def _engine_sizing(suggested: str = "Standard_D2s_v3") -> VmSizingRecommendation:
    return VmSizingRecommendation(
        action="downgrade",
        current_sku="Standard_D4s_v3",
        suggested_sku=suggested,
        current_family="D",
        suggested_family="D",
        family_label="General purpose",
        direction="down",
        avg_cpu_pct=5.0,
        avg_memory_pct=10.0,
        confidence=70,
        reasons=["Low utilization."],
    )


def _advisor(target: str = "Standard_D4s_v3", savings: float | None = None) -> AdvisorVmTarget:
    return AdvisorVmTarget(
        resource_id="/subscriptions/s/rg/providers/microsoft.compute/virtualmachines/vm1",
        recommendation_id="rec-1",
        current_sku="Standard_D8s_v3",
        target_sku=target,
        recommendation_type_id="39a8510b-812c-4530-ab2a-c8491f9bf666",
        potential_savings_monthly=savings,
        summary="Resize VM",
    )


@patch("app.vm_cost_decision.compute_vm_resize_pricing")
def test_engine_savings_preserved_when_advisor_savings_null(mock_pricing):
    mock_pricing.side_effect = [
        (122.0, {"pricing_status": "available", "savings_basis": "monthly_run_rate"}),
        (100.0, {"pricing_status": "available"}),
    ]
    vm = {"location": "eastus", "properties": {"storageProfile": {"osDisk": {"osType": "Linux"}}}}
    decision = resolve_vm_cost_decision(
        vm=vm,
        current_sku="Standard_D8s_v3",
        engine_sizing=_engine_sizing("Standard_D2s_v3"),
        advisor=_advisor("Standard_D4s_v3", savings=None),
        monthly_cost=63.0,
    )
    assert decision is not None
    assert decision.target_sku == "Standard_D4s_v3"
    assert decision.monthly_savings == pytest.approx(122.0)
    assert decision.sku_agreement == "disagree"


@patch("app.vm_cost_decision.compute_vm_resize_pricing")
def test_falls_back_to_engine_sku_savings_when_advisor_pricing_zero(mock_pricing):
    mock_pricing.side_effect = [
        (0.0, {"pricing_status": "unavailable"}),
        (85.0, {"pricing_status": "available", "savings_basis": "retail_list"}),
    ]
    vm = {"location": "eastus", "properties": {"storageProfile": {"osDisk": {"osType": "Linux"}}}}
    decision = resolve_vm_cost_decision(
        vm=vm,
        current_sku="Standard_D8s_v3",
        engine_sizing=_engine_sizing("Standard_D2s_v3"),
        advisor=_advisor("Standard_B4ms", savings=None),
        monthly_cost=50.0,
    )
    assert decision is not None
    assert decision.monthly_savings == pytest.approx(85.0)
    assert decision.pricing.get("savings_fallback") == "engine_target_sku"


@patch("app.vm_cost_decision.compute_vm_resize_pricing")
def test_sku_agreement_when_targets_match(mock_pricing):
    mock_pricing.return_value = (70.0, {"pricing_status": "available"})
    vm = {"location": "eastus", "properties": {"storageProfile": {"osDisk": {"osType": "Linux"}}}}
    decision = resolve_vm_cost_decision(
        vm=vm,
        current_sku="Standard_D4s_v3",
        engine_sizing=_engine_sizing("Standard_D2s_v3"),
        advisor=_advisor("Standard_D2s_v3", savings=244.0),
        monthly_cost=100.0,
    )
    assert decision is not None
    assert decision.sku_agreement == "agree"
    assert decision.monthly_savings == pytest.approx(70.0)
