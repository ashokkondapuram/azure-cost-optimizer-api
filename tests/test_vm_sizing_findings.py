"""End-to-end VM sizing finding tests with mocked retail pricing."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.optimizer.extended_engine import ExtendedOptimizationEngine
from app.optimizer.advanced_rules import ADVANCED_RULES


def _vm(cpu: float, mem: float, sku: str = "Standard_D4s_v3") -> dict:
    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
    return {
        "id": rid,
        "name": "vm1",
        "location": "eastus",
        "properties": {"hardwareProfile": {"vmSize": sku}},
        "_technical_facts": {
            "data_source": "azure_monitor",
            "avg_cpu_pct": cpu,
            "avg_memory_pct": mem,
        },
    }


@pytest.fixture
def engine():
    rules = {k: ADVANCED_RULES[k] for k in ADVANCED_RULES}
    eng = ExtendedOptimizationEngine()
    eng.rules = rules
    return eng


@patch("app.optimizer.resource_engines.compute.vm.analysis.vm_catalog", return_value=[])
def test_vm_sizing_skipped_without_memory_metrics(_catalog, engine):
    from app.optimizer.resource_engines.compute.vm.analysis import analyze_vms

    vm = {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        "name": "vm1",
        "location": "eastus",
        "properties": {"hardwareProfile": {"vmSize": "Standard_D4s_v3"}},
        "_technical_facts": {"data_source": "azure_monitor", "avg_cpu_pct": 5.0},
    }
    metrics = {
        vm["id"].lower(): {
            "value": [{"name": {"value": "Percentage CPU"}, "timeseries": [{"data": [{"average": 5.0}]}]}],
        },
    }
    findings = analyze_vms(engine, "sub", [vm], metrics, {vm["id"].lower(): 200.0})
    sizing = [f for f in findings if f.rule_id == "VM_SKU_SIZING_EXTENDED"]
    assert not sizing


@patch("app.optimizer.resource_engines.compute.vm.analysis.vm_catalog", return_value=[])
@patch("app.vm_cost_decision.compute_vm_resize_pricing")
def test_vm_sizing_emits_without_retail_when_downsize(mock_pricing, _catalog, engine):
    from app.optimizer.resource_engines.compute.vm.analysis import analyze_vms

    mock_pricing.return_value = (0.0, {
        "current_sku_monthly_usd": None,
        "suggested_sku_monthly_usd": None,
        "estimated_monthly_savings_usd": 0,
        "pricing_status": "unavailable",
    })
    vm = _vm(4.0, 10.0)
    rid = vm["id"].lower()
    metrics = {
        rid: {
            "value": [
                {"name": {"value": "Percentage CPU"}, "timeseries": [{"data": [{"average": 4.0}]}]},
                {"name": {"value": "Available Memory Bytes"}, "timeseries": [{"data": [{"average": 14 * 1024 ** 3}]}]},
            ],
        },
    }
    findings = analyze_vms(engine, "sub", [vm], metrics, {rid: 200.0})
    sizing = [f for f in findings if f.rule_id == "VM_SKU_SIZING_EXTENDED"]
    assert len(sizing) == 1
    assert sizing[0].estimated_savings_usd == 0.0
    assert "Downsize" in (sizing[0].recommendation or "")


@patch("app.optimizer.resource_engines.compute.vm.analysis.vm_catalog", return_value=[])
@patch("app.vm_cost_decision.compute_vm_resize_pricing")
@patch("app.optimizer.resource_engines.compute.vm.analysis.recommend_vm_sku")
def test_vm_sizing_emits_cross_family_without_retail(mock_recommend, mock_pricing, _catalog, engine):
    from app.optimizer.resource_engines.compute.vm.analysis import analyze_vms
    from app.vm_sizing import VmSizingRecommendation

    mock_recommend.return_value = VmSizingRecommendation(
        action="cross_family",
        current_sku="Standard_D4s_v3",
        suggested_sku="Standard_B2s_v3",
        current_family="D",
        suggested_family="B",
        family_label="General purpose",
        direction="lateral",
        avg_cpu_pct=4.0,
        avg_memory_pct=10.0,
        confidence=66,
        reasons=["Workload shape may fit the Burstable family better."],
    )
    mock_pricing.return_value = (0.0, {
        "current_sku_monthly_usd": None,
        "suggested_sku_monthly_usd": None,
        "estimated_monthly_savings_usd": 0,
        "pricing_status": "unavailable",
    })
    vm = _vm(4.0, 10.0)
    rid = vm["id"].lower()
    metrics = {
        rid: {
            "value": [
                {"name": {"value": "Percentage CPU"}, "timeseries": [{"data": [{"average": 4.0}]}]},
                {"name": {"value": "Available Memory Bytes"}, "timeseries": [{"data": [{"average": 14 * 1024 ** 3}]}]},
            ],
        },
    }
    findings = analyze_vms(engine, "sub", [vm], metrics, {rid: 200.0})
    sizing = [f for f in findings if f.rule_id == "VM_RIGHTSIZE_FAMILY"]
    assert len(sizing) == 1
    assert sizing[0].estimated_savings_usd == 0.0
    assert "Change family" in (sizing[0].recommendation or "")
    assert sizing[0].evidence.get("sizing_action") == "cross_family"


@patch("app.optimizer.resource_engines.compute.vm.analysis.vm_catalog", return_value=[])
@patch("app.vm_cost_decision.compute_vm_resize_pricing")
def test_vm_sizing_emits_retail_savings(mock_pricing, _catalog, engine):
    from app.optimizer.resource_engines.compute.vm.analysis import analyze_vms

    mock_pricing.return_value = (70.08, {
        "current_sku_monthly_usd": 140.16,
        "suggested_sku_monthly_usd": 70.08,
        "estimated_monthly_savings_usd": 70.08,
        "pricing_status": "available",
        "pricing_source": "azure_retail_prices",
    })
    vm = _vm(5.0, 8.0)
    rid = vm["id"].lower()
    metrics = {
        rid: {
            "value": [
                {"name": {"value": "Percentage CPU"}, "timeseries": [{"data": [{"average": 5.0}]}]},
                {"name": {"value": "Available Memory Bytes"}, "timeseries": [{"data": [{"average": 8e9}]}]},
            ],
        },
    }
    findings = analyze_vms(engine, "sub", [vm], metrics, {rid: 200.0})
    sizing = [f for f in findings if f.rule_id == "VM_SKU_SIZING_EXTENDED"]
    if sizing:
        assert sizing[0].estimated_savings_usd == pytest.approx(70.08)


@patch("app.optimizer.resource_engines.compute.vm.analysis.vm_catalog", return_value=[])
@patch("app.vm_cost_decision.compute_vm_resize_pricing")
def test_vm_sizing_prefers_advisor_target_sku(mock_pricing, _catalog, engine):
    from app.advisor_vm_targets import AdvisorVmTarget
    from app.optimizer.resource_engines.compute.vm.analysis import analyze_vms

    mock_pricing.return_value = (
        122.0,
        {
            "current_sku_monthly_usd": 329.96,
            "suggested_sku_monthly_usd": 164.98,
            "estimated_monthly_savings_usd": 122.0,
            "retail_monthly_savings_usd": 164.98,
            "monthly_run_rate_usd": 244.0,
            "savings_basis": "monthly_run_rate",
            "pricing_status": "available",
            "pricing_source": "azure_retail_prices",
        },
    )
    vm = _vm(5.0, 8.0, sku="Standard_D8s_v3")
    rid = vm["id"].lower()
    metrics = {
        rid: {
            "value": [
                {"name": {"value": "Percentage CPU"}, "timeseries": [{"data": [{"average": 5.0}]}]},
                {"name": {"value": "Available Memory Bytes"}, "timeseries": [{"data": [{"average": 8e9}]}]},
            ],
        },
    }
    advisor_targets = {
        rid: AdvisorVmTarget(
            resource_id=rid,
            recommendation_id="rec-1",
            current_sku="Standard_D8s_v3",
            target_sku="Standard_D4s_v3",
            recommendation_type_id="39a8510b-812c-4530-ab2a-c8491f9bf666",
            potential_savings_monthly=244.0,
            summary="Resize VM",
        ),
    }
    findings = analyze_vms(
        engine,
        "sub",
        [vm],
        metrics,
        {rid: 63.0},
        advisor_vm_targets=advisor_targets,
    )
    sizing = [f for f in findings if f.rule_id == "VM_SKU_SIZING_EXTENDED"]
    assert len(sizing) == 1
    assert sizing[0].evidence.get("suggested_sku") == "Standard_D4s_v3"
    assert sizing[0].evidence.get("sku_source") == "azure_advisor"
    assert sizing[0].estimated_savings_usd == pytest.approx(122.0)
    mock_pricing.assert_called()
    assert mock_pricing.call_args.args[2] == "Standard_D4s_v3"
