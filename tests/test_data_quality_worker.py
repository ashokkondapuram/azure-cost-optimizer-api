"""Tests for data quality assessment worker."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data_store.enrichment_registry import ensure_all_enrichment_tables, get_enrichment_model
from app.models import Base, ResourceAssessmentResult, ResourceSnapshot
from app.workers.data_quality_worker import run_data_quality_worker


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    ensure_all_enrichment_tables(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _disk_resource(sub: str = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee") -> ResourceSnapshot:
    rid = f"/subscriptions/{sub}/resourcegroups/rg/providers/microsoft.compute/disks/disk1"
    return ResourceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id=sub,
        resource_id=rid,
        resource_name="disk1",
        resource_type="compute/disk",
        resource_group="rg",
        location="eastus",
        sku="Premium_LRS",
        state="Succeeded",
        properties_json=json.dumps({"diskState": "Attached", "diskSizeGB": 128}),
        tags_json=json.dumps({}),
        is_active=True,
        is_cost_export_only=False,
        monthly_cost_usd=0.0,
        synced_at=datetime.now(timezone.utc),
    )


def test_data_quality_worker_caps_missing_metrics(db_session, monkeypatch):
    monkeypatch.setenv("DATA_QUALITY_WORKER_ENABLED", "true")
    sub = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    inv = _disk_resource(sub)
    db_session.add(inv)
    db_session.flush()
    disk_model = get_enrichment_model("compute/disk")
    db_session.add(
        disk_model(
            id=str(uuid.uuid4()),
            subscription_id=sub,
            resource_id=inv.id,
            arm_id=inv.resource_id,
            snapshot_json=json.dumps({"metrics": {}}),
            pipeline_stage="metrics_ready",
        )
    )
    db_session.commit()

    result = run_data_quality_worker(db_session, sub)
    assert result["status"] == "ok"
    assert result["assessed"] == 1

    row = (
        db_session.query(ResourceAssessmentResult)
        .filter(ResourceAssessmentResult.resource_id == inv.resource_id)
        .one()
    )
    assert row.score <= 74
