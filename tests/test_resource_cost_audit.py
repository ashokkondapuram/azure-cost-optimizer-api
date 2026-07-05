"""Tests for cost-first resource type audit."""

from __future__ import annotations

import uuid
from collections import Counter
from unittest.mock import MagicMock, patch

from app.models import CostByResourceTypeSnapshot
from app.resource_cost_audit import build_resource_cost_audit, load_mtd_cost_by_arm_type


def test_build_resource_cost_audit_skips_free_unmapped():
    arm_counts = Counter({
        "microsoft.managedidentity/userassignedidentities": 50,
        "microsoft.network/trafficmanagerprofiles": 10,
        "microsoft.compute/disks": 100,
    })
    cost_by_arm = {
        "microsoft.network/trafficmanagerprofiles": {
            "cost_usd": 250.0,
            "cost_billing": 300.0,
            "billing_currency": "CAD",
            "canonical_resource_type": "other/microsoft.network-trafficmanagerprofiles",
        },
        "microsoft.compute/disks": {
            "cost_usd": 5000.0,
            "cost_billing": 6000.0,
            "billing_currency": "CAD",
            "canonical_resource_type": "compute/disk",
        },
    }

    audit = build_resource_cost_audit(arm_counts, cost_by_arm, month="2026-06")

    assert audit["free_skipped_unmapped_count"] == 50
    assert "microsoft.managedidentity/userassignedidentities" in audit["free_skipped_unmapped_types"]
    assert len(audit["gaps"]) == 1
    assert audit["gaps"][0]["arm_type"] == "microsoft.network/trafficmanagerprofiles"
    assert audit["gaps"][0]["cost_usd"] == 250.0
    assert any(row["arm_type"] == "microsoft.compute/disks" for row in audit["synced_cost_types"])


def test_load_mtd_cost_by_arm_type_from_db():
    from app.database import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        sub = f"audit-sub-{uuid.uuid4().hex[:8]}"
        db.add(
            CostByResourceTypeSnapshot(
                id=str(uuid.uuid4()),
                subscription_id=sub,
                arm_resource_type="microsoft.compute/virtualmachines",
                canonical_resource_type="compute/vm",
                month="2026-06",
                cost_usd=1200.0,
                cost_billing=1500.0,
                billing_currency="CAD",
            )
        )
        db.commit()

        cost_map, month = load_mtd_cost_by_arm_type(db, sub, month="2026-06")
        assert month == "2026-06"
        assert cost_map["microsoft.compute/virtualmachines"]["cost_usd"] == 1200.0
    finally:
        db.close()
