"""Tests for Azure inventory technical fact extraction."""

from app.cost_export_recommendations import _row_to_finding, COST_EXPORT_RULES
from app.finding_evidence import enrich_finding_for_api
from app.inventory_technical import (
    arm_resource_type_for_finding,
    technical_facts_from_inventory_row,
)
from app.resource_store import apply_costs_to_resources


VM_ID = (
    "/subscriptions/abc/resourceGroups/prod-rg/providers/"
    "Microsoft.Compute/virtualMachines/prod-vm-01"
)


def test_technical_facts_from_synced_vm():
    row = {
        "id": VM_ID,
        "type": "compute/vm",
        "name": "prod-vm-01",
        "location": "eastus",
        "resourceGroup": "prod-rg",
        "state": "running",
        "sku": "Standard_D4s_v3",
        "properties": {
            "hardwareProfile": {"vmSize": "Standard_D4s_v3"},
            "powerState": "PowerState/running",
        },
    }
    facts = technical_facts_from_inventory_row(row)
    assert facts["data_source"] == "synced_inventory"
    assert facts["arm_resource_type"] == "microsoft.compute/virtualmachines"
    assert facts["location"] == "eastus"
    assert facts["vm_size"] == "Standard_D4s_v3"
    assert facts["power_state"] == "running"


def test_technical_facts_skip_cost_export_stub():
    row = {
        "id": VM_ID,
        "type": "compute/vm",
        "properties": {"source": "cost_export"},
    }
    assert technical_facts_from_inventory_row(row) == {}


def test_apply_costs_does_not_overwrite_inventory_service_name():
    row = {
        "id": VM_ID,
        "azureServiceName": "Virtual Machines",
        "properties": {"hardwareProfile": {"vmSize": "Standard_B2s"}},
    }
    apply_costs_to_resources([row], {
        VM_ID.lower(): {
            "pretax": 120.0,
            "usd": 120.0,
            "currency": "USD",
            "service_name": "Bandwidth",
        }
    })
    assert row["azureServiceName"] == "Virtual Machines"
    assert row["billingServiceName"] == "Bandwidth"


def test_cost_export_finding_uses_inventory_technical_not_billing():
    rule = next(r for r in COST_EXPORT_RULES if r.id == "COST_HIGH_SPEND_REVIEW")
    row = {
        "id": VM_ID,
        "type": "compute/vm",
        "name": "prod-vm-01",
        "location": "eastus",
        "resourceGroup": "prod-rg",
        "state": "running",
        "sku": "Standard_D4s_v3",
        "billingServiceName": "Virtual Machines",
        "monthlyCostBilling": 500.0,
        "monthlyCostUsd": 500.0,
        "inInventory": True,
        "properties": {
            "hardwareProfile": {"vmSize": "Standard_D4s_v3"},
            "powerState": "PowerState/running",
        },
    }
    finding = _row_to_finding("abc", row, rule, 500.0)
    assert finding["resource_type"] == "microsoft.compute/virtualmachines"
    assert finding["location"] == "eastus"
    assert finding["evidence"]["vm_size"] == "Standard_D4s_v3"
    assert finding["evidence"]["azure_service_name"] == "Virtual Machines"

    enriched = enrich_finding_for_api(finding)
    details = enriched["evidence"]["resource_details"]
    assert details.get("vm_size") == "Standard_D4s_v3"
    assert details.get("location") == "eastus"
    assert "azure_service_name" not in details
    assert "Virtual Machines" not in str(details.values())


def test_arm_resource_type_from_id():
    assert arm_resource_type_for_finding(VM_ID, "compute/vm") == "microsoft.compute/virtualmachines"
