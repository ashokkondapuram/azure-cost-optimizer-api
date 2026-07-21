"""Read-path tests for enrichment-backed dashboard, drawer, and list APIs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.dashboard.api import _latest_utilization_by_resource, _mtd_cost_by_resource_ids
from app.data_store.enrichment_registry import clear_all_enrichment_tables, ensure_enrichment_table, get_enrichment_model
from app.data_store.resource_enrichment import upsert_cost, upsert_metrics, upsert_recommendations
from app.models import Base, CostByResourceSnapshot, ResourceSnapshot
from app.resource_enrichment import (
    advanced_analysis_from_enrichment,
    enrichment_drawer_entry,
    load_enrichment_batch,
    mtd_costs_map_from_enrichment,
    overlay_list_rows_from_enrichment,
    utilization_map_from_enrichment,
)
from app.resource_store import get_resources_db

SUBSCRIPTION_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
RESOURCE_ID = (
    f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/rg/providers/"
    "Microsoft.Compute/virtualMachines/vm-read"
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    ensure_enrichment_table(engine, "compute/vm")
    Session = sessionmaker(bind=engine)
    session = Session()
    snap = ResourceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id=SUBSCRIPTION_ID,
        resource_id=RESOURCE_ID.lower(),
        resource_name="vm-read",
        resource_type="compute/vm",
        resource_group="rg",
        location="eastus",
        monthly_cost_usd=80.0,
        monthly_cost_billing=100.0,
        billing_currency="CAD",
        is_active=True,
        synced_at=datetime.now(timezone.utc),
    )
    session.add(snap)
    session.commit()
    yield session, snap
    session.close()


def test_overlay_list_rows_from_enrichment(db_session):
    db, snap = db_session
    upsert_metrics(
        db,
        snap,
        {},
        metrics_payload={
            "ok": True,
            "facts": {"avg_cpu_pct": 22.0},
            "metrics": [],
            "derived": [],
        },
    )
    upsert_cost(db, snap)
    db.commit()

    rows = [{"id": RESOURCE_ID, "name": "vm-read", "type": "compute/vm"}]
    enriched = overlay_list_rows_from_enrichment(db, SUBSCRIPTION_ID, rows)
    assert enriched[0]["metricsFacts"]["avg_cpu_pct"] == pytest.approx(22.0)
    assert enriched[0]["monthlyCostUsd"] == pytest.approx(80.0)


def test_get_resources_db_overlays_enrichment(db_session):
    db, snap = db_session
    upsert_metrics(
        db,
        snap,
        {},
        metrics_payload={
            "ok": True,
            "facts": {"avg_cpu_pct": 9.5},
            "metrics": [],
            "derived": [],
        },
    )
    db.commit()

    items = get_resources_db(
        db,
        SUBSCRIPTION_ID,
        "compute/vm",
        unpaginated=True,
    )
    match = next(item for item in items if item["id"] == RESOURCE_ID.lower())
    assert match["metricsFacts"]["avg_cpu_pct"] == pytest.approx(9.5)


def test_dashboard_utilization_and_cost_maps(db_session):
    db, snap = db_session
    upsert_metrics(
        db,
        snap,
        {},
        metrics_payload={
            "ok": True,
            "facts": {"avg_cpu_pct": 15.0},
            "metrics": [],
            "derived": [],
        },
    )
    upsert_cost(db, snap)
    db.commit()

    util = utilization_map_from_enrichment(db, SUBSCRIPTION_ID, [RESOURCE_ID])
    assert util[RESOURCE_ID.lower()] == "15.0%"

    costs = mtd_costs_map_from_enrichment(db, SUBSCRIPTION_ID, [RESOURCE_ID])
    assert costs[RESOURCE_ID.lower()] == pytest.approx(100.0)

    panel_util = _latest_utilization_by_resource(db, SUBSCRIPTION_ID, [RESOURCE_ID])
    assert panel_util[RESOURCE_ID.lower()] == "15.0%"

    panel_cost = _mtd_cost_by_resource_ids(db, SUBSCRIPTION_ID, [RESOURCE_ID])
    assert panel_cost[RESOURCE_ID.lower()] == pytest.approx(100.0)


def test_advanced_analysis_from_enrichment(db_session):
    db, snap = db_session
    upsert_recommendations(
        db,
        snap,
        summary=[{"rule_id": "VM_IDLE", "severity": "HIGH"}],
        findings_count=1,
        savings_usd=55.0,
        top_severity="HIGH",
    )
    db.commit()

    batch = load_enrichment_batch(db, SUBSCRIPTION_ID, [RESOURCE_ID])
    analysis = advanced_analysis_from_enrichment(batch[RESOURCE_ID.lower()], slim=True)
    assert analysis["insights"]["headline"]
    assert analysis["insights"]["estimated_savings_usd"] == pytest.approx(55.0)


def test_overlay_falls_back_when_no_enrichment(db_session):
    db, _snap = db_session
    rows = [{"id": RESOURCE_ID, "monthlyCostUsd": 80.0}]
    assert overlay_list_rows_from_enrichment(db, SUBSCRIPTION_ID, rows) == rows

    vm_model = get_enrichment_model("compute/vm")
    clear_all_enrichment_tables(db)
    assert db.query(vm_model).count() == 0


def test_overlay_does_not_stomp_row_cost_with_stale_zero_enrichment(db_session):
    """Stale enrichment cost_pending rows must not erase live cost_map/snapshot billing."""
    db, snap = db_session
    disk_id = (
        f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/rg/providers/"
        "Microsoft.Compute/disks/disk-cost"
    )
    disk_snap = ResourceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id=SUBSCRIPTION_ID,
        resource_id=disk_id.lower(),
        resource_name="disk-cost",
        resource_type="compute/disk",
        resource_group="rg",
        location="canadacentral",
        monthly_cost_usd=0.0,
        monthly_cost_billing=0.0,
        billing_currency="CAD",
        is_active=True,
        synced_at=datetime.now(timezone.utc),
    )
    db.add(disk_snap)
    db.commit()

    ensure_enrichment_table(db.get_bind(), "compute/disk")
    upsert_cost(db, disk_snap)
    db.commit()

    rows = [{
        "id": disk_id,
        "name": "disk-cost",
        "type": "compute/disk",
        "monthlyCostBilling": 55.0,
        "monthlyCostUsd": 40.0,
        "billingCurrency": "CAD",
    }]
    enriched = overlay_list_rows_from_enrichment(db, SUBSCRIPTION_ID, rows)
    assert enriched[0]["cost"]["billed_mtd"] == pytest.approx(55.0)
    assert enriched[0]["cost"]["cost_pending"] is False


def test_enrichment_drawer_entry_reads_batch_snapshot_cost(db_session):
    db, snap = db_session
    upsert_cost(db, snap)
    db.commit()

    batch = load_enrichment_batch(db, SUBSCRIPTION_ID, [RESOURCE_ID])
    entry = enrichment_drawer_entry(
        batch[RESOURCE_ID.lower()],
        include_metrics=False,
        include_recommendations=False,
    )
    assert entry["cost"]["billed_mtd"] == pytest.approx(100.0)
    assert entry["monthlyCostBilling"] == pytest.approx(100.0)
    assert entry["monthlyCostUsd"] == pytest.approx(80.0)


def test_mtd_costs_map_prefers_cost_overlay_keys(db_session):
    db, snap = db_session
    snap.monthly_cost_usd = 0.0
    snap.monthly_cost_billing = 0.0
    db.add(
        CostByResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=SUBSCRIPTION_ID,
            resource_id=RESOURCE_ID.lower(),
            service_name="Virtual Machines",
            month=datetime.now(timezone.utc).strftime("%Y-%m"),
            cost_usd=55.0,
            cost_billing=70.0,
            billing_currency="CAD",
        )
    )
    db.commit()

    from app.data_store.resource_enrichment import sync_cost_for_subscription

    sync_cost_for_subscription(db, SUBSCRIPTION_ID)
    db.commit()

    costs = mtd_costs_map_from_enrichment(db, SUBSCRIPTION_ID, [RESOURCE_ID])
    assert costs[RESOURCE_ID.lower()] == pytest.approx(70.0)
