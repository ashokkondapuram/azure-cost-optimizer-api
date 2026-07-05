"""Tests for commitment finding deduplication."""
from __future__ import annotations

import copy

from app.commitment_findings import dedupe_commitment_findings
from app.optimizer.extended_engine import ExtendedOptimizationEngine
from app.optimizer.advanced_rules import ADVANCED_RULES
from app.optimizer.resource_engines.cost.commitments.analysis import analyze_commitments


def _vm(rid_suffix: str, sku: str = "Standard_D4s_v3", cost_key: str | None = None) -> dict:
    rid = f"/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/{rid_suffix}"
    return {
        "id": rid,
        "name": rid_suffix,
        "location": "eastus",
        "properties": {
            "hardwareProfile": {"vmSize": sku},
            "instanceView": {
                "statuses": [{"code": "PowerState/running"}],
            },
        },
    }


def _finding(rule_id: str, resource_id: str, **kwargs) -> dict:
    base = {
        "rule_id": rule_id,
        "rule_name": rule_id,
        "resource_id": resource_id,
        "estimated_savings_usd": 100.0,
        "evidence": {"scope": "subscription"},
    }
    base.update(kwargs)
    return base


def test_dedupe_removes_per_vm_commitment_when_subscription_exists():
    vm_rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
    findings = [
        _finding("RESERVED_OPPORTUNITY_EXTENDED", vm_rid),
        _finding("VM_COMMITMENT_CANDIDATE", vm_rid, evidence={"uptime_hours": 900}),
        _finding("VM_COMMITMENT_CANDIDATE", vm_rid + "2", evidence={"uptime_hours": 900}),
    ]
    out = dedupe_commitment_findings(findings)
    rule_ids = {f["rule_id"] for f in out}
    assert "VM_COMMITMENT_CANDIDATE" not in rule_ids
    assert "RESERVED_OPPORTUNITY_EXTENDED" in rule_ids


def test_dedupe_merges_ri_and_savings_plan_subscription_findings():
    vm_rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
    findings = [
        _finding("RESERVED_OPPORTUNITY_EXTENDED", vm_rid, estimated_savings_usd=300.0),
        _finding("SAVINGS_PLAN_OPPORTUNITY_EXTENDED", vm_rid, estimated_savings_usd=250.0),
    ]
    out = dedupe_commitment_findings(findings)
    assert len(out) == 1
    merged = out[0]
    assert merged["rule_id"] == "SAVINGS_PLAN_OPPORTUNITY_EXTENDED"
    assert "Reserved Instances" in merged["recommendation"]
    assert "Savings Plan" in merged["recommendation"]
    assert merged["estimated_savings_usd"] == 300.0
    assert merged["evidence"]["commitment_options"] == ["reserved_instance", "savings_plan"]


def test_analyze_commitments_emits_single_combined_finding():
    rules = {k: copy.deepcopy(ADVANCED_RULES[k]) for k in ADVANCED_RULES}
    engine = ExtendedOptimizationEngine()
    engine.rules = rules
    vms = [_vm("vm1"), _vm("vm2")]
    costs = {vms[0]["id"].lower(): 400.0, vms[1]["id"].lower(): 350.0}
    findings = analyze_commitments(engine, "sub", vms, costs, subscription_spend_usd=2000.0)
    rule_ids = [f.rule_id for f in findings]
    assert rule_ids.count("SAVINGS_PLAN_OPPORTUNITY_EXTENDED") == 1
    assert "RESERVED_OPPORTUNITY_EXTENDED" not in rule_ids
    options = findings[0].evidence.get("commitment_options") or []
    option_ids = [row.get("option") for row in options if isinstance(row, dict)]
    assert "reserved_instance_1yr" in option_ids
    assert "savings_plan_1yr" in option_ids
    assert findings[0].evidence.get("commitment_comparison")
