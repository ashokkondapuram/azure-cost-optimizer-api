"""Load Balancer monitor metrics and optimization rules."""

from __future__ import annotations

from app.azure_monitor_aggregations import lookup_supported_aggregations
from app.azure_retail_pricing import estimate_load_balancer_monthly_price
from app.load_balancer_catalog import load_load_balancer_specifications, parse_load_balancer_arm
from app.metrics_catalog import build_derived_metric_rows
from app.monitor_metrics import enrich_derived_monitor_facts
from app.optimizer.advanced_rules import ADVANCED_RULES
from app.optimizer.resource_engines.network.loadbalancer.analysis import analyze_load_balancers
from app.optimizer.resource_engines.network.loadbalancer.optimization_rules import (
    evaluate_lb_idle_no_backends,
    evaluate_lb_snat_pressure,
    evaluate_lb_throughput_rightsize,
)
from app.resources.registry import profiles_for_canonical


def test_load_balancer_threshold_catalog():
    specs = load_load_balancer_specifications()
    assert specs.get("schema_version") == 1
    assert specs.get("optimization_thresholds", {}).get("snat_pressure_pct") == 70.0


def test_load_balancer_monitor_profile_aggregations():
    profile = profiles_for_canonical("network/loadbalancer")[0]
    for metric in profile.metrics:
        assert lookup_supported_aggregations(profile.monitor_arm_type, metric.metric_name)
    peak = next(m for m in profile.metrics if m.fact_key == "byte_count_peak")
    assert peak.aggregation == "Maximum"


def test_load_balancer_idle_no_backends():
    lb = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/loadBalancers/lb1",
        "name": "lb1",
        "sku": {"name": "Standard"},
        "properties": {"backendAddressPools": [{"name": "pool1", "properties": {}}]},
    }
    draft = evaluate_lb_idle_no_backends(
        lb, parse_load_balancer_arm(lb), 0.0, ADVANCED_RULES["LOAD_BALANCER_IDLE_EXTENDED"],
    )
    assert draft is not None
    assert draft.savings > 0


def test_load_balancer_snat_pressure():
    lb = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/loadBalancers/lb1",
        "name": "lb1",
        "sku": {"name": "Standard"},
        "properties": {
            "backendAddressPools": [
                {"name": "pool1", "properties": {"backendIPConfigurations": [{"id": "x"}]}},
            ],
        },
        "_technical_facts": {
            "used_snat_ports": 800.0,
            "allocated_snat_ports": 1000.0,
            "snat_port_usage_pct": 80.0,
            "data_source": "azure_monitor",
        },
    }
    draft = evaluate_lb_snat_pressure(
        lb, parse_load_balancer_arm(lb), 50.0, ADVANCED_RULES["LOAD_BALANCER_SNAT_PRESSURE"],
    )
    assert draft is not None
    assert draft.priority == "P1"


def test_load_balancer_throughput_rightsize():
    lb = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/loadBalancers/lb1",
        "name": "lb1",
        "sku": {"name": "Standard"},
        "properties": {
            "backendAddressPools": [
                {"name": "pool1", "properties": {"backendIPConfigurations": [{"id": "x"}]}},
            ],
        },
        "_technical_facts": {
            "byte_count": 1000.0,
            "byte_count_peak": 50000.0,
            "data_source": "azure_monitor",
        },
    }
    draft = evaluate_lb_throughput_rightsize(
        lb, parse_load_balancer_arm(lb), 60.0, ADVANCED_RULES["LOAD_BALANCER_THROUGHPUT_RIGHTSIZE"],
    )
    assert draft is not None
    assert draft.rule_id == "LOAD_BALANCER_THROUGHPUT_RIGHTSIZE"


def test_load_balancer_derived_snat_port_usage():
    lb = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/loadBalancers/lb1",
        "sku": {"name": "Standard"},
        "properties": {},
    }
    enriched = enrich_derived_monitor_facts(
        lb,
        "network/loadbalancer",
        {"used_snat_ports": 700.0, "allocated_snat_ports": 1000.0},
        metrics={},
    )
    assert enriched["snat_port_usage_pct"] == 70.0
    derived = build_derived_metric_rows(enriched, canonical_type="network/loadbalancer")
    assert any(row["fact_key"] == "snat_port_usage_pct" for row in derived)


def test_load_balancer_catalog_pricing_stub():
    pricing = estimate_load_balancer_monthly_price()
    assert pricing["pricing_status"] == "available"
    assert pricing["estimated_monthly_usd"] > 0


class _FakeEngine:
    rules = ADVANCED_RULES

    def _extract_rg(self, rid: str) -> str:
        parts = (rid or "").split("/")
        if "resourceGroups" in parts:
            idx = parts.index("resourceGroups")
            return parts[idx + 1] if idx + 1 < len(parts) else ""
        return ""

    def _finding(self, **kwargs):
        from datetime import datetime, timezone
        from app.optimizer.core.finding import ExtendedFinding

        rule = kwargs.pop("rule")
        resource = kwargs.get("resource") or {}
        rid = resource.get("id") or ""
        savings = float(kwargs.get("savings", 0) or 0)
        return ExtendedFinding(
            rule_id=rule.id,
            rule_name=rule.name,
            category=rule.category.value,
            severity=rule.severity.value,
            subscription_id=kwargs.get("subscription_id", ""),
            resource_id=rid,
            resource_name=resource.get("name") or "",
            resource_type=resource.get("type") or "",
            resource_group=self._extract_rg(rid),
            location=resource.get("location") or "",
            detail=kwargs.get("detail", ""),
            recommendation=kwargs.get("recommendation", ""),
            estimated_savings_usd=round(savings, 2),
            annualized_savings_usd=round(savings * 12, 2),
            waste_score=kwargs.get("waste_score", 0),
            confidence_score=kwargs.get("confidence", 0),
            action_priority=kwargs.get("priority", "P3"),
            impact=kwargs.get("impact", ""),
            evidence=kwargs.get("evidence") or {},
            tags=resource.get("tags") or {},
            detected_at=datetime.now(timezone.utc).isoformat(),
        )


def test_load_balancer_analyze_idle_extended():
    lb = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/loadBalancers/lb1",
        "name": "lb1",
        "sku": {"name": "Standard"},
        "properties": {"backendAddressPools": [{"name": "pool1", "properties": {}}]},
    }
    findings = analyze_load_balancers(_FakeEngine(), "sub", [lb], {lb["id"].lower(): 60.0})
    assert any(f.rule_id == "LOAD_BALANCER_IDLE_EXTENDED" for f in findings)
