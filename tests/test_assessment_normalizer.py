"""Tests for assessment normalized record builder."""

from __future__ import annotations

from app.assessment.normalizer import build_normalized_record


def test_disk_normalized_record_shape():
    row_dict = {
        "subscription_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "resource_id": "/subscriptions/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/resourceGroups/rg/providers/Microsoft.Compute/disks/disk1",
        "resource_name": "disk1",
        "resource_type": "Microsoft.Compute/disks",
        "canonical_type": "compute-disk",
        "resource_group": "rg",
        "location": "eastus",
        "sku": "Premium_LRS",
        "state": "Succeeded",
        "properties": {
            "diskState": "Unattached",
            "diskSizeGB": 128,
            "tier": "P10",
        },
        "tags": {"Environment": "prod"},
        "monthly_cost_usd": 12.5,
        "monthly_cost_billing": 12.5,
        "billing_currency": "USD",
    }
    metrics = {
        "Composite Disk Read Bytes/sec": 1024.0,
        "Composite Disk Write Bytes/sec": 512.0,
    }

    record = build_normalized_record(row_dict, metrics=metrics)

    assert record["resource_type"] == "Microsoft.Compute/disks"
    assert record["properties"]["diskState"] == "Unattached"
    assert record["properties"]["diskSizeGB"] == 128
    assert record["cost"]["monthlyActualCost"] == 12.5
    assert record["metrics"]["Composite Disk Read Bytes/sec"] == 1024.0
    assert record["resource"]["name"] == "disk1"
    assert record["tags"]["Environment"] == "prod"
    assert "missingRequiredMetrics" in record["signals"]
    assert record["signals"]["missingCostData"] is False
