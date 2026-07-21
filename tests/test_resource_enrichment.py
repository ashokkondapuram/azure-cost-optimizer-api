"""Tests for per-type resource enrichment store."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data_store.enrichment_registry import (
    clear_all_enrichment_tables,
    ensure_enrichment_table,
    get_enrichment_model,
)
from app.data_store.resource_enrichment import (
    enrichment_max_age_hours,
    load_metrics_payload_from_store,
    upsert_metrics,
    upsert_recommendations,
    utilization_by_type_from_enrichment,
)
from app.models import Base, ResourceSnapshot

SUBSCRIPTION_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
RESOURCE_ID = (
    f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/rg/providers/"
    "Microsoft.Compute/virtualMachines/vm-enrich"
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    ensure_enrichment_table(engine, "compute/vm")
    Session = sessionmaker(bind=engine)
    db = Session()
    snapshot = ResourceSnapshot(
        id="snap-enrich-1",
        subscription_id=SUBSCRIPTION_ID,
        resource_id=RESOURCE_ID.lower(),
        resource_name="vm-enrich",
        resource_type="compute/vm",
        resource_group="rg",
        location="eastus",
        monthly_cost_usd=120.0,
        monthly_cost_billing=150.0,
        billing_currency="CAD",
        is_active=True,
    )
    db.add(snapshot)
    db.commit()
    yield db
    db.close()


def test_persist_and_load_metrics_enrichment(db_session):
    snapshot = db_session.query(ResourceSnapshot).one()
    payload = {
        "ok": True,
        "resource_id": RESOURCE_ID.lower(),
        "canonical_type": "compute/vm",
        "timespan": "P7D",
        "data_quality": "azure_monitor",
        "facts": {"avg_cpu_pct": 12.5},
        "metrics": [{"fact_key": "avg_cpu_pct", "label": "CPU", "stats": {"average": 12.5}}],
        "derived": [],
        "metrics_raw": {"value": [{"large": "blob"}]},
    }
    upsert_metrics(db_session, snapshot, payload["facts"], metrics_payload=payload)
    db_session.commit()

    loaded = load_metrics_payload_from_store(
        db_session, RESOURCE_ID, canonical_type="compute/vm",
    )
    assert loaded is not None
    assert loaded["source"] == "db"
    assert loaded["facts"]["avg_cpu_pct"] == pytest.approx(12.5)
    assert "metrics_raw" not in loaded

    vm_model = get_enrichment_model("compute/vm")
    row = (
        db_session.query(vm_model)
        .filter(vm_model.arm_id == RESOURCE_ID.lower())
        .one()
    )
    assert row.metrics_at is not None


def test_stale_enrichment_not_returned(db_session, monkeypatch):
    monkeypatch.setenv("ENRICHMENT_MAX_AGE_HOURS", "1")
    snapshot = db_session.query(ResourceSnapshot).one()
    upsert_metrics(
        db_session,
        snapshot,
        {"avg_cpu_pct": 5.0},
        metrics_payload={"ok": True, "facts": {"avg_cpu_pct": 5.0}, "metrics": [], "derived": []},
    )
    db_session.commit()
    vm_model = get_enrichment_model("compute/vm")
    row = db_session.query(vm_model).one()
    row.metrics_at = datetime.now(timezone.utc) - timedelta(hours=3)
    db_session.commit()

    assert enrichment_max_age_hours() == 1.0
    assert load_metrics_payload_from_store(
        db_session, RESOURCE_ID, max_age_hours=1.0, canonical_type="compute/vm",
    ) is None


def test_persist_recommendations_enrichment(db_session):
    snapshot = db_session.query(ResourceSnapshot).one()
    upsert_recommendations(
        db_session,
        snapshot,
        summary=[{"rule_id": "VM_IDLE", "severity": "HIGH", "estimated_savings_usd": 40}],
        findings_count=1,
        savings_usd=40.0,
        top_severity="HIGH",
    )
    db_session.commit()
    vm_model = get_enrichment_model("compute/vm")
    row = db_session.query(vm_model).one()
    assert row.analysis_at is not None


def test_utilization_by_type_from_enrichment(db_session):
    snapshot = db_session.query(ResourceSnapshot).one()
    upsert_metrics(
        db_session,
        snapshot,
        {"avg_cpu_pct": 18.0},
        metrics_payload={
            "ok": True,
            "facts": {"avg_cpu_pct": 18.0},
            "metrics": [],
            "derived": [],
        },
    )
    db_session.commit()

    items = utilization_by_type_from_enrichment(db_session, SUBSCRIPTION_ID, limit=6)
    assert items
    assert items[0]["count"] >= 1
    assert items[0]["avg_utilization_pct"] == pytest.approx(18.0)
