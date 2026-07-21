"""Tests for per-resource retail price estimation."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.cost_utils import attach_cost_envelope_to_row, build_resource_cost_envelope, finalize_cost_block
from app.resource_retail_cost import estimate_resource_retail_monthly
from app.resource_store import apply_costs_to_resources


def test_build_resource_cost_envelope_both_values():
    envelope = build_resource_cost_envelope(
        billing=42.5,
        usd=33.0,
        currency="CAD",
        retail_monthly=89.0,
        retail_currency="USD",
        retail_source="azure_retail_prices",
        retail_pending=False,
        cost_pending=False,
    )
    assert envelope["billed_mtd"] == pytest.approx(42.5)
    assert envelope["retail_monthly"] == pytest.approx(89.0)
    assert envelope["retail_source"] == "azure_retail_prices"
    assert envelope["cost_pending"] is False


def test_finalize_cost_block_includes_nested_cost():
    block = finalize_cost_block({
        "monthly_cost_billing": 55.0,
        "billing_currency": "CAD",
        "retail_monthly": 70.0,
        "retail_currency": "USD",
        "retail_source": "azure_retail_prices",
        "retail_pending": False,
    })
    assert block["cost"]["billed_mtd"] == pytest.approx(55.0)
    assert block["cost"]["retail_monthly"] == pytest.approx(70.0)


def test_attach_cost_envelope_to_row_flat_and_nested():
    row = {"name": "vm1", "billingCurrency": "CAD"}
    envelope = build_resource_cost_envelope(
        billing=10.0,
        currency="CAD",
        retail_monthly=25.0,
        retail_currency="USD",
        retail_source="azure_retail_prices",
        retail_pending=False,
        cost_pending=False,
    )
    attach_cost_envelope_to_row(row, envelope)
    assert row["monthlyCostBilling"] == pytest.approx(10.0)
    assert row["retailMonthly"] == pytest.approx(25.0)
    assert row["cost"]["billed_mtd"] == pytest.approx(10.0)


@patch("app.azure_retail_pricing.get_vm_monthly_price", return_value=150.0)
def test_estimate_vm_retail_monthly(mock_price):
    result = estimate_resource_retail_monthly({
        "type": "compute/vm",
        "location": "eastus",
        "sku": "Standard_D2s_v3",
        "properties": {
            "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
            "storageProfile": {"osDisk": {"osType": "Linux"}},
        },
        "billingCurrency": "CAD",
    })
    assert result["retail_monthly"] == pytest.approx(150.0)
    assert result["retail_source"] == "azure_retail_prices"
    assert result["retail_pending"] is False


@patch("app.azure_retail_pricing.get_managed_disk_monthly_price", return_value=18.5)
def test_estimate_disk_retail_monthly(mock_price):
    result = estimate_resource_retail_monthly({
        "type": "compute/disk",
        "location": "eastus",
        "sku": "Premium_LRS",
        "properties": {"diskSizeGB": 128},
        "billingCurrency": "CAD",
    })
    assert result["retail_monthly"] == pytest.approx(18.5)
    mock_price.assert_called_once()


def test_apply_costs_to_resources_enriches_row():
    rows = [{
        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/disks/d1",
        "type": "compute/disk",
        "location": "eastus",
        "sku": "Premium_LRS",
        "properties": {"diskSizeGB": 64},
        "monthlyCostBilling": 12.0,
        "billingCurrency": "CAD",
    }]
    cost_map = {
        "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/d1": {
            "pretax": 12.0,
            "usd": 9.5,
            "currency": "CAD",
        },
    }
    with patch("app.resource_retail_cost.estimate_resource_retail_monthly", return_value={
        "retail_monthly": 22.0,
        "retail_currency": "USD",
        "retail_source": "azure_retail_prices",
        "retail_pending": False,
    }):
        enriched = apply_costs_to_resources(rows, cost_map)
    assert enriched[0]["cost"]["billed_mtd"] == pytest.approx(12.0)
    assert enriched[0]["cost"]["retail_monthly"] == pytest.approx(22.0)
