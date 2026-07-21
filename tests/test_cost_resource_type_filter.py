"""Tests for cost queries filtered by resource type."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.cost_db import cost_summary_from_db
from app.models import Base, CostByResourceTypeSnapshot, CostSyncRun
from app.resource_type_catalog import expand_resource_type_filter, resource_types_catalog


def test_expand_resource_type_filter_category_prefix():
    expanded = expand_resource_type_filter(["compute"])
    assert "compute/vm" in expanded
    assert "compute/disk" in expanded
    assert "storage/account" not in expanded


def test_resource_types_catalog_has_groups():
    catalog = resource_types_catalog()
    assert catalog["count"] > 10
    assert any(group["category"] == "Compute" for group in catalog["categories"])


def test_cost_summary_filtered_by_resource_type():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    sub = "sub-1"
    month = "2026-06"
    db.add(
        CostByResourceTypeSnapshot(
            id="vm",
            subscription_id=sub,
            arm_resource_type="microsoft.compute/virtualmachines",
            canonical_resource_type="compute/vm",
            month=month,
            cost_usd=100.0,
            cost_billing=120.0,
            billing_currency="CAD",
            synced_at=datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
        )
    )
    db.add(
        CostByResourceTypeSnapshot(
            id="storage",
            subscription_id=sub,
            arm_resource_type="microsoft.storage/storageaccounts",
            canonical_resource_type="storage/account",
            month=month,
            cost_usd=50.0,
            cost_billing=60.0,
            billing_currency="CAD",
            synced_at=datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
        )
    )
    db.add(
        CostSyncRun(
            id="run-1",
            subscription_id=sub,
            month=month,
            mtd_start="2026-06-01",
            mtd_end="2026-06-30",
            total_billing=180.0,
            total_usd=150.0,
            billing_currency="CAD",
            services_json="[]",
            changes_json="[]",
            synced_at=datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
        )
    )
    db.commit()

    all_summary = cost_summary_from_db(db, sub, timeframe="MonthToDate", month=month)
    assert all_summary is not None
    assert all_summary["pretax_total"] == 180.0

    compute_summary = cost_summary_from_db(
        db, sub, timeframe="MonthToDate", month=month, resource_types=["compute/vm"],
    )
    assert compute_summary is not None
    assert compute_summary["pretax_total"] == 120.0
    assert compute_summary["total_source"] == "resource_type_rows_sum"
    assert compute_summary["resource_types"] == ["compute/vm"]

    all_types = list(resource_types_catalog()["types"])
    all_canonical = [row["canonical"] for row in all_types]
    full_filter_summary = cost_summary_from_db(
        db, sub, timeframe="MonthToDate", month=month, resource_types=all_canonical,
    )
    assert full_filter_summary is not None
    assert full_filter_summary["pretax_total"] == 180.0
    assert full_filter_summary.get("total_source") != "resource_type_rows_sum"

    db.close()
