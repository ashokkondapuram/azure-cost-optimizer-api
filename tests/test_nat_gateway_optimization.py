"""NAT Gateway monitor metrics and optimization rules."""

from __future__ import annotations

from app.azure_monitor_aggregations import lookup_supported_aggregations
from app.metrics_catalog import build_derived_metric_rows
from app.monitor_metrics import enrich_derived_monitor_facts
from app.nat_gateway_catalog import (
    load_nat_gateway_specifications,
    parse_nat_gateway_arm,
    snat_capacity_for_gateway,
)
from app.optimizer.advanced_rules import ADVANCED_RULES
from app.optimizer.resource_engines.network.nat.analysis import analyze_nat_gateways
from app.optimizer.resource_engines.network.nat.optimization_rules import (
    evaluate_nat_idle_unassociated,
    evaluate_nat_snat_exhaustion,
)
from app.resources.registry import profiles_for_canonical


def test_nat_gateway_threshold_catalog():
    specs = load_nat_gateway_specifications()
    assert specs.get("schema_version") == 1
    assert specs.get("optimization_thresholds", {}).get("snat_exhaustion_pct") == 80.0


def test_nat_monitor_profile_aggregations():
    profile = profiles_for_canonical("network/nat")[0]
    for metric in profile.metrics:
        assert lookup_supported_aggregations(profile.monitor_arm_type, metric.metric_name)


def test_nat_snat_exhaustion_finding():
    nat = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/natGateways/nat1",
        "name": "nat1",
        "sku": {"name": "Standard"},
        "properties": {
            "subnets": [{"id": "/subscriptions/s/.../subnets/s1"}],
            "publicIpAddresses": [{"id": "/subscriptions/s/.../publicIPAddresses/p1"}],
        },
        "_technical_facts": {"snat_connection_count": 52000.0, "data_source": "azure_monitor"},
    }
    ctx = parse_nat_gateway_arm(nat)
    draft = evaluate_nat_snat_exhaustion(nat, ctx, 40.0, ADVANCED_RULES["NAT_GATEWAY_SNAT_EXHAUSTION"])
    assert draft is not None
    assert draft.rule_id == "NAT_GATEWAY_SNAT_EXHAUSTION"
    assert draft.priority == "P1"


def test_nat_idle_unassociated_savings():
    nat = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/natGateways/nat1",
        "name": "nat1",
        "sku": {"name": "Standard"},
        "properties": {"subnets": [], "publicIpAddresses": []},
    }
    draft = evaluate_nat_idle_unassociated(
        nat, parse_nat_gateway_arm(nat), 0.0, ADVANCED_RULES["NAT_GATEWAY_IDLE_EXTENDED"],
    )
    assert draft is not None
    assert draft.savings > 0


def test_nat_derived_snat_utilization():
    nat = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/natGateways/nat1",
        "sku": {"name": "Standard"},
        "properties": {
            "publicIpAddresses": [{"id": "p1"}],
            "subnets": [{"id": "s1"}],
        },
    }
    enriched = enrich_derived_monitor_facts(
        nat, "network/nat", {"snat_connection_count": 30000.0}, metrics={},
    )
    assert enriched["snat_utilization_pct"] > 0
    assert snat_capacity_for_gateway(nat) == 64512
    derived = build_derived_metric_rows(enriched, canonical_type="network/nat")
    assert any(row["fact_key"] == "snat_utilization_pct" for row in derived)


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


def test_nat_analyze_idle_extended():
    nat = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/natGateways/nat1",
        "name": "nat1",
        "sku": {"name": "Standard"},
        "properties": {"subnets": [], "publicIpAddresses": []},
    }
    findings = analyze_nat_gateways(_FakeEngine(), "sub", [nat], {nat["id"].lower(): 35.0})
    assert any(f.rule_id == "NAT_GATEWAY_IDLE_EXTENDED" for f in findings)
