"""Tests for Azure Retail Prices API integration."""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from app import azure_retail_pricing as pricing


def _vm_item(product_name: str, retail_price: float, *, sku_name: str = "D4s v3") -> dict:
    return {
        "currencyCode": "USD",
        "retailPrice": retail_price,
        "unitOfMeasure": "1 Hour",
        "armSkuName": "Standard_D4s_v3",
        "productName": product_name,
        "skuName": sku_name,
        "serviceName": "Virtual Machines",
        "priceType": "Consumption",
    }


@pytest.fixture(autouse=True)
def clear_pricing_cache():
    pricing._CACHE.clear()
    pricing._NEGATIVE_CACHE.clear()
    yield
    pricing._CACHE.clear()
    pricing._NEGATIVE_CACHE.clear()


def test_pick_hourly_price_prefers_linux():
    items = [
        _vm_item("Virtual Machines Dsv3 Series Windows", 0.384),
        _vm_item("Virtual Machines Dsv3 Series Linux", 0.192),
    ]
    assert pricing._pick_hourly_price(items, os_type="linux") == 0.192


def test_get_vm_monthly_price_from_retail():
    with patch.object(pricing, "_fetch_retail_items") as fetch:
        fetch.return_value = [_vm_item("Virtual Machines Dsv3 Series Linux", 0.10)]
        monthly = pricing.get_vm_monthly_price("eastus", "Standard_D4s_v3", os_type="linux")
    assert monthly == pytest.approx(73.0)


def test_estimate_vm_sku_savings_retail_delta():
    def side_effect(filter_expr: str):
        if "Standard_D4s_v3" in filter_expr:
            return [_vm_item("Virtual Machines Dsv3 Series Linux", 0.20)]
        if "Standard_D2s_v3" in filter_expr:
            return [_vm_item("Virtual Machines Dsv3 Series Linux", 0.10)]
        return []

    with patch.object(pricing, "_fetch_retail_items", side_effect=side_effect):
        result = pricing.estimate_vm_sku_savings(
            "eastus",
            "Standard_D4s_v3",
            "Standard_D2s_v3",
            os_type="linux",
        )

    assert result["current_sku_monthly_usd"] == pytest.approx(146.0)
    assert result["suggested_sku_monthly_usd"] == pytest.approx(73.0)
    assert result["estimated_monthly_savings_usd"] == pytest.approx(73.0)


def test_estimate_vm_sku_savings_scales_with_actual_cost():
    def side_effect(filter_expr: str):
        if "Standard_D4s_v3" in filter_expr:
            return [_vm_item("Virtual Machines Dsv3 Series Linux", 0.20)]
        if "Standard_D2s_v3" in filter_expr:
            return [_vm_item("Virtual Machines Dsv3 Series Linux", 0.10)]
        return []

    with patch.object(pricing, "_fetch_retail_items", side_effect=side_effect):
        result = pricing.estimate_vm_sku_savings(
            "eastus",
            "Standard_D4s_v3",
            "Standard_D2s_v3",
            os_type="linux",
            actual_monthly_cost=200.0,
        )

    assert result["estimated_monthly_savings_usd"] == pytest.approx(100.0)


def test_estimate_disk_tier_savings():
    premium_items = [{
        "retailPrice": 19.71,
        "unitOfMeasure": "1 Month",
        "productName": "Premium SSD Managed Disks",
        "skuName": "P30 LRS",
        "priceType": "Consumption",
    }]
    ssd_items = [{
        "retailPrice": 7.68,
        "unitOfMeasure": "1 Month",
        "productName": "Standard SSD Managed Disks",
        "skuName": "E30 LRS",
        "priceType": "Consumption",
    }]

    def side_effect(filter_expr: str):
        if "Premium SSD" in filter_expr:
            return premium_items
        if "Standard SSD" in filter_expr:
            return ssd_items
        return []

    with patch.object(pricing, "_fetch_retail_items", side_effect=side_effect):
        result = pricing.estimate_disk_tier_savings(
            "eastus",
            128,
            "Premium_LRS",
            "StandardSSD_LRS",
        )

    assert result["current_tier_monthly_usd"] == pytest.approx(19.71)
    assert result["suggested_tier_monthly_usd"] == pytest.approx(7.68)
    assert result["estimated_monthly_savings_usd"] == pytest.approx(12.03)


def test_savings_from_retail_delta_helper():
    from app.cost_utils import savings_from_retail_delta

    assert savings_from_retail_delta({"estimated_monthly_savings_usd": 42.5}) == 42.5
    assert savings_from_retail_delta(None) == 0.0


def test_fetch_retail_items_retries_on_429():
    resp_429 = Mock(status_code=429, headers={"Retry-After": "0"})
    resp_200 = Mock(status_code=200, headers={})
    resp_200.json.return_value = {
        "Items": [_vm_item("Virtual Machines Dsv3 Series Linux", 0.10)],
        "NextPageLink": None,
    }
    resp_200.raise_for_status = Mock()

    with patch.object(pricing, "_pause_between_retail_requests"), patch.object(pricing.time, "sleep"), patch(
        "app.azure_retail_pricing.requests.get", side_effect=[resp_429, resp_200],
    ):
        items = pricing._fetch_retail_items(
            "serviceName eq 'Virtual Machines' and armRegionName eq 'eastus'"
        )

    assert len(items) == 1


def test_fetch_retail_items_uses_negative_cache_after_rate_limit():
    resp_429 = Mock(status_code=429, headers={})
    mock_get = Mock(return_value=resp_429)

    with patch.object(pricing, "_pause_between_retail_requests"), patch.object(pricing.time, "sleep"), patch(
        "app.azure_retail_pricing.requests.get", mock_get,
    ), patch.object(pricing, "retail_price_max_retries", return_value=1):
        filt = "serviceName eq 'Virtual Machines' and armRegionName eq 'westus3'"
        assert pricing._fetch_retail_items(filt) == []
        assert pricing._fetch_retail_items(filt) == []
    assert mock_get.call_count == 1
