"""Tests for networking optimization batch 1 — Public IP, NAT Gateway, Load Balancer."""

from __future__ import annotations

from app.load_balancer_catalog import load_load_balancer_specifications, parse_load_balancer_arm
from app.nat_gateway_catalog import load_nat_gateway_specifications, parse_nat_gateway_arm, snat_capacity_for_gateway
from app.optimizer.advanced_rules import ADVANCED_RULES
from app.optimizer.resource_engines.network.loadbalancer.analysis import analyze_load_balancers
from app.optimizer.resource_engines.network.loadbalancer.optimization_rules import evaluate_lb_idle_no_backends, evaluate_lb_snat_pressure
from app.optimizer.resource_engines.network.nat.analysis import analyze_nat_gateways
from app.optimizer.resource_engines.network.nat.optimization_rules import evaluate_nat_idle_unassociated, evaluate_nat_snat_exhaustion
from app.optimizer.resource_engines.network.publicip.analysis import analyze_public_ips
from app.optimizer.resource_engines.network.publicip.optimization_rules import evaluate_public_ip_basic_sku_migration
from app.public_ip_catalog import load_public_ip_specifications, parse_public_ip_arm
from app.monitor_metrics import enrich_derived_monitor_facts


class _FakeEngine:
    def __init__(self):
        self.rules = ADVANCED_RULES

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


def _public_ip(*, sku="Standard", static=True, associated=False, facts=None):
    props = {
        "publicIPAllocationMethod": "Static" if static else "Dynamic",
        "provisioningState": "Succeeded",
    }
    if associated:
        props["ipConfiguration"] = {"id": "/subscriptions/s/.../ipConfigs/nic"}
    row = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/pip1",
        "name": "pip1",
        "location": "eastus",
        "sku": {"name": sku, "tier": sku},
        "properties": props,
    }
    if facts:
        row["_technical_facts"] = {**facts, "data_source": "azure_monitor"}
    return row


def test_catalog_json_loads():
    assert load_public_ip_specifications().get("schema_version") == 1
    assert load_nat_gateway_specifications().get("schema_version") == 1
    assert load_load_balancer_specifications().get("schema_version") == 1


def test_public_ip_basic_sku_migration():
    ip = _public_ip(sku="Basic")
    ctx = parse_public_ip_arm(ip)
    draft = evaluate_public_ip_basic_sku_migration(
        ip, ctx, 3.0, ADVANCED_RULES["PUBLIC_IP_BASIC_SKU_MIGRATION"],
    )
    assert draft is not None
    assert draft.rule_id == "PUBLIC_IP_BASIC_SKU_MIGRATION"
    assert draft.priority == "P2"


def test_public_ip_analyze_unassociated():
    engine = _FakeEngine()
    findings = analyze_public_ips(
        engine, "sub", [_public_ip(static=True, associated=False)], {"": 0},
    )
    assert any(f.rule_id == "PUBLIC_IP_IDLE_EXTENDED" for f in findings)


def test_nat_snat_exhaustion():
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
    assert draft.priority == "P1"
    assert draft.rule_id == "NAT_GATEWAY_SNAT_EXHAUSTION"


def test_nat_idle_savings_without_mtd_cost():
    nat = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/natGateways/nat1",
        "name": "nat1",
        "sku": {"name": "Standard"},
        "properties": {"subnets": [], "publicIpAddresses": []},
    }
    ctx = parse_nat_gateway_arm(nat)
    draft = evaluate_nat_idle_unassociated(nat, ctx, 0.0, ADVANCED_RULES["NAT_GATEWAY_IDLE_EXTENDED"])
    assert draft is not None
    assert draft.savings > 0


def test_load_balancer_idle_savings_without_mtd_cost():
    lb = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/loadBalancers/lb1",
        "name": "lb1",
        "sku": {"name": "Standard"},
        "properties": {"backendAddressPools": [{"name": "pool1", "properties": {}}]},
    }
    ctx = parse_load_balancer_arm(lb)
    draft = evaluate_lb_idle_no_backends(lb, ctx, 0.0, ADVANCED_RULES["LOAD_BALANCER_IDLE_EXTENDED"])
    assert draft is not None
    assert draft.savings > 0


def test_nat_analyze_idle():
    engine = _FakeEngine()
    nat = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/natGateways/nat1",
        "name": "nat1",
        "sku": {"name": "Standard"},
        "properties": {"subnets": [], "publicIpAddresses": []},
    }
    findings = analyze_nat_gateways(engine, "sub", [nat], {nat["id"].lower(): 35.0})
    assert any(f.rule_id == "NAT_GATEWAY_IDLE_EXTENDED" for f in findings)


def test_load_balancer_snat_pressure():
    lb = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/loadBalancers/lb1",
        "name": "lb1",
        "sku": {"name": "Standard"},
        "properties": {
            "backendAddressPools": [{"name": "pool1", "properties": {"backendIPConfigurations": [{"id": "x"}]}}],
        },
        "_technical_facts": {
            "used_snat_ports": 800.0,
            "allocated_snat_ports": 1000.0,
            "snat_port_usage_pct": 80.0,
            "data_source": "azure_monitor",
        },
    }
    ctx = parse_load_balancer_arm(lb)
    draft = evaluate_lb_snat_pressure(lb, ctx, 50.0, ADVANCED_RULES["LOAD_BALANCER_SNAT_PRESSURE"])
    assert draft is not None
    assert draft.priority == "P1"


def test_enrich_derived_snat_facts():
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

    lb = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/loadBalancers/lb1",
        "sku": {"name": "Standard"},
        "properties": {},
    }
    lb_enriched = enrich_derived_monitor_facts(
        lb, "network/loadbalancer",
        {"used_snat_ports": 700.0, "allocated_snat_ports": 1000.0},
        metrics={},
    )
    assert lb_enriched["snat_port_usage_pct"] == 70.0


def test_load_balancer_analyze_empty_backends():
    engine = _FakeEngine()
    lb = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/loadBalancers/lb1",
        "name": "lb1",
        "sku": {"name": "Standard"},
        "properties": {
            "backendAddressPools": [{"name": "pool1", "properties": {}}],
        },
    }
    findings = analyze_load_balancers(engine, "sub", [lb], {lb["id"].lower(): 60.0})
    assert any(f.rule_id == "LOAD_BALANCER_IDLE_EXTENDED" for f in findings)
