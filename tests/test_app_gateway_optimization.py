"""Application Gateway monitor metrics and optimization rules."""

from __future__ import annotations

from app.app_gateway_catalog import load_app_gateway_specifications, parse_app_gateway_arm
from app.azure_monitor_aggregations import lookup_supported_aggregations
from app.azure_retail_pricing import estimate_app_gateway_monthly_price
from app.metrics_catalog import build_derived_metric_rows
from app.monitor_metrics import enrich_derived_monitor_facts
from app.optimizer.advanced_rules import ADVANCED_RULES
from app.optimizer.resource_engines.network.appgateway.optimization_rules import (
    evaluate_app_gateway_cu_rightsize,
    evaluate_app_gateway_cu_saturation,
)
from app.resources.registry import profiles_for_canonical


def test_app_gateway_threshold_catalog():
    specs = load_app_gateway_specifications()
    assert specs.get("schema_version") == 1
    assert specs.get("optimization_thresholds", {}).get("cu_saturation_pct") == 80.0


def test_app_gateway_monitor_profile_aggregations():
    profile = profiles_for_canonical("network/appgateway")[0]
    for metric in profile.metrics:
        assert lookup_supported_aggregations(profile.monitor_arm_type, metric.metric_name)


def test_app_gateway_cu_saturation():
    gw = {
        "name": "agw1",
        "sku": {"tier": "WAF_v2", "capacity": 2},
        "_technical_facts": {"billed_capacity_units": 180.0, "data_source": "azure_monitor"},
    }
    draft = evaluate_app_gateway_cu_saturation(
        gw, parse_app_gateway_arm(gw), 350.0, ADVANCED_RULES["APP_GATEWAY_CU_SATURATION"],
    )
    assert draft is not None
    assert draft.priority == "P1"
    assert draft.rule_id == "APP_GATEWAY_CU_SATURATION"


def test_app_gateway_cu_rightsize_down():
    gw = {
        "name": "agw1",
        "sku": {"tier": "Standard_v2", "capacity": 4},
        "_technical_facts": {"billed_capacity_units": 80.0, "data_source": "azure_monitor"},
    }
    draft = evaluate_app_gateway_cu_rightsize(
        gw, parse_app_gateway_arm(gw), 500.0, ADVANCED_RULES["APP_GATEWAY_CU_RIGHTSIZE_DOWN"],
    )
    assert draft is not None
    assert draft.rule_id == "APP_GATEWAY_CU_RIGHTSIZE_DOWN"
    assert draft.savings >= 0


def test_app_gateway_derived_cu_utilization():
    gw = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/applicationGateways/agw1",
        "sku": {"tier": "Standard_v2", "capacity": 2},
    }
    enriched = enrich_derived_monitor_facts(
        gw, "network/appgateway", {"billed_capacity_units": 120.0}, metrics={},
    )
    assert enriched["cu_utilization_pct"] == 60.0
    derived = build_derived_metric_rows(enriched, canonical_type="network/appgateway")
    assert any(row["fact_key"] == "cu_utilization_pct" for row in derived)


def test_app_gateway_catalog_pricing_stub():
    pricing = estimate_app_gateway_monthly_price(tier="Standard_v2", capacity=2)
    assert pricing["pricing_status"] == "available"
    assert pricing["estimated_monthly_usd"] > 0


def test_app_gateway_rules_registered():
    for rule_id in (
        "APP_GATEWAY_IDLE_EXTENDED",
        "APP_GATEWAY_CU_SATURATION",
        "APP_GATEWAY_CU_RIGHTSIZE_DOWN",
    ):
        assert rule_id in ADVANCED_RULES
