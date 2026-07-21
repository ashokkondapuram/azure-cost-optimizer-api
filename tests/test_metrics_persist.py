"""Fast tests for Azure Monitor metrics persistence on fetch."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data_store.enrichment_registry import ensure_enrichment_table, get_enrichment_model
from app.data_store.resource_enrichment import get_enrichment_row, load_enrichment_dict
from app.metrics_api import (
    _persist_batch_metrics_enrichment,
    _persist_metrics_enrichment_safe,
    fetch_metrics_for_resource,
    fetch_metrics_for_subscription,
)
from app.models import Base, ResourceSnapshot

SUBSCRIPTION_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
RESOURCE_ID = (
    f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/rg/providers/"
    "Microsoft.Compute/virtualMachines/vm-metrics"
)
AKS_RESOURCE_ID = (
    f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/rg/providers/"
    "Microsoft.ContainerService/managedClusters/aks-cluster"
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    ensure_enrichment_table(engine, "compute/vm")
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(
        ResourceSnapshot(
            id="snap-metrics-1",
            subscription_id=SUBSCRIPTION_ID,
            resource_id=RESOURCE_ID.lower(),
            resource_name="vm-metrics",
            resource_type="compute/vm",
            resource_group="rg",
            location="eastus",
            monthly_cost_usd=80.0,
            is_active=True,
            synced_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    yield db
    db.close()


def test_persist_metrics_enrichment_safe_writes_resource_enrichment(db_session):
    response = {
        "ok": True,
        "resource_id": RESOURCE_ID.lower(),
        "canonical_type": "compute/vm",
        "timespan": "P7D",
        "data_quality": "azure_monitor",
        "facts": {"avg_cpu_pct": 22.0},
        "metrics": [],
        "derived": [],
    }
    monitor_raw = {"value": [{"name": {"value": "Percentage CPU"}, "timeseries": []}]}

    _persist_metrics_enrichment_safe(
        db_session,
        RESOURCE_ID,
        response,
        monitor_raw=monitor_raw,
    )

    row = get_enrichment_row(db_session, SUBSCRIPTION_ID, RESOURCE_ID)
    assert row is not None
    loaded = load_enrichment_dict(row)
    assert loaded["metrics"]["avg_cpu_pct"] == pytest.approx(22.0)
    assert loaded["metrics"]["payload"]["ok"] is True
    assert loaded["metrics"]["monitor_raw"] == monitor_raw
    assert loaded["metrics_at"] is not None


def test_persist_batch_metrics_enrichment_writes_enrichment_rows(db_session):
    resources = [{"id": RESOURCE_ID}]
    facts = {RESOURCE_ID.lower(): {"avg_cpu_pct": 15.0}}
    raw = {RESOURCE_ID.lower(): {"value": [{"name": {"value": "Percentage CPU"}}]}}

    _persist_batch_metrics_enrichment(
        db_session,
        SUBSCRIPTION_ID,
        resources,
        facts,
        timespan="P7D",
        resource_metrics=raw,
    )

    row = get_enrichment_row(db_session, SUBSCRIPTION_ID, RESOURCE_ID)
    assert row is not None
    metrics = json.loads(row.metrics_json or "{}")
    assert metrics["avg_cpu_pct"] == pytest.approx(15.0)
    assert metrics["monitor_raw"] == raw[RESOURCE_ID.lower()]


@patch("app.metrics_api.load_azure_monitor_metrics")
@patch("app.cost_db.resource_cost_map_from_db", return_value={})
@patch("app.metrics_api.list_all_resources_db")
def test_fetch_metrics_for_subscription_persists_batch(
    mock_list_resources,
    _mock_cost_map,
    mock_load_metrics,
    db_session,
):
    mock_list_resources.return_value = [
        {
            "id": RESOURCE_ID,
            "name": "vm-metrics",
            "type": "compute/vm",
            "canonical_type": "compute/vm",
        }
    ]
    mock_load_metrics.return_value = (
        {RESOURCE_ID.lower(): {"value": []}},
        {RESOURCE_ID.lower(): {"avg_cpu_pct": 9.5}},
        {"requested": 1, "loaded": 1},
    )

    result = fetch_metrics_for_subscription(db_session, SUBSCRIPTION_ID, timespan="P7D")

    assert result["ok"] is True
    row = get_enrichment_row(db_session, SUBSCRIPTION_ID, RESOURCE_ID)
    assert row is not None
    metrics = json.loads(row.metrics_json or "{}")
    assert metrics["avg_cpu_pct"] == pytest.approx(9.5)


@patch("app.metrics_api._inventory_baseline_response")
@patch("app.metrics_api.get_monitor_profile", return_value=None)
def test_fetch_metrics_for_resource_skips_missing_enrichment_table(
    _mock_profile,
    mock_baseline,
    db_session,
):
    """Missing per-type enrichment table must not 500 — fall through to fetch path."""
    mock_baseline.return_value = {
        "ok": True,
        "resource_id": RESOURCE_ID.lower(),
        "data_quality": "inventory_baseline",
        "facts": {},
        "metrics": [],
        "derived": [],
    }

    result = fetch_metrics_for_resource(
        RESOURCE_ID,
        timespan="P7D",
        db=db_session,
        refresh=False,
    )

    assert result["ok"] is True
    mock_baseline.assert_called_once()


@patch("app.metrics_api._inventory_baseline_response")
@patch("app.metrics_api.get_monitor_profile", return_value=None)
def test_fetch_metrics_for_aks_skips_missing_enrichment_table(
    _mock_profile,
    mock_baseline,
    db_session,
):
    """AKS /metrics/resource/auto path must tolerate missing resource_enrichment_containers_aks."""
    aks_snap = ResourceSnapshot(
        id="snap-aks-1",
        subscription_id=SUBSCRIPTION_ID,
        resource_id=AKS_RESOURCE_ID.lower(),
        resource_name="aks-cluster",
        resource_type="containers/aks",
        resource_group="rg",
        location="eastus",
        is_active=True,
        synced_at=datetime.now(timezone.utc),
    )
    db_session.add(aks_snap)
    db_session.commit()

    mock_baseline.return_value = {
        "ok": True,
        "resource_id": AKS_RESOURCE_ID.lower(),
        "canonical_type": "containers/aks",
        "data_quality": "inventory_baseline",
        "facts": {},
        "metrics": [],
        "derived": [],
    }

    result = fetch_metrics_for_resource(
        AKS_RESOURCE_ID,
        timespan="P7D",
        db=db_session,
        refresh=False,
    )

    assert result["ok"] is True
    assert result["canonical_type"] == "containers/aks"
    mock_baseline.assert_called_once()


def test_aks_metrics_persist_is_idempotent(db_session):
    """Repeated AKS metrics persist must not violate uq_re_containers_aks_sub_arm."""
    ensure_enrichment_table(db_session.get_bind(), "containers/aks")
    aks_snap = ResourceSnapshot(
        id="snap-aks-2",
        subscription_id=SUBSCRIPTION_ID,
        resource_id=AKS_RESOURCE_ID.lower(),
        resource_name="aks-cluster",
        resource_type="containers/aks",
        resource_group="rg",
        location="eastus",
        is_active=True,
        synced_at=datetime.now(timezone.utc),
    )
    db_session.add(aks_snap)
    db_session.commit()

    response = {
        "ok": True,
        "resource_id": AKS_RESOURCE_ID.lower(),
        "canonical_type": "containers/aks",
        "timespan": "P7D",
        "data_quality": "azure_monitor",
        "facts": {"cluster_cpu_pct": 41.0},
        "metrics": [],
        "derived": [],
    }

    _persist_metrics_enrichment_safe(db_session, AKS_RESOURCE_ID, response)
    _persist_metrics_enrichment_safe(db_session, AKS_RESOURCE_ID, response)

    model = get_enrichment_model("containers/aks")
    rows = (
        db_session.query(model)
        .filter(
            model.subscription_id == SUBSCRIPTION_ID,
            model.arm_id == AKS_RESOURCE_ID.lower(),
        )
        .all()
    )
    assert len(rows) == 1
    metrics = json.loads(rows[0].metrics_json or "{}")
    assert metrics["cluster_cpu_pct"] == pytest.approx(41.0)
