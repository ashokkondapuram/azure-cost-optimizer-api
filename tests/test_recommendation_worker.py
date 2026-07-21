"""Tests for assessment recommendation worker."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data_store.enrichment_registry import ensure_all_enrichment_tables, get_enrichment_model
from app.models import Base, ResourceAssessmentResult, ResourceSnapshot
from app.workers.recommendation_worker import run_recommendation_worker


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    ensure_all_enrichment_tables(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_recommendation_worker_emits_unattached_disk_finding(db_session, monkeypatch):
    monkeypatch.setenv("RECOMMENDATION_WORKER_ENABLED", "true")
    monkeypatch.setenv("LEGACY_SUB_ENGINES_ENABLED", "true")
    sub = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    rid = f"/subscriptions/{sub}/resourcegroups/rg/providers/microsoft.compute/disks/disk1"

    snapshot = {
        "resource_id": rid,
        "resource_type": "Microsoft.Compute/disks",
        "resource": {"name": "disk1", "resource_group": "rg", "location": "eastus"},
        "properties": {"diskState": "Unattached"},
        "metrics": {},
        "cost": {"monthlyActualCost": 20.0},
        "tags": {},
        "policy": {},
        "signals": {"missingRequiredMetrics": True},
    }

    db_session.add(
        ResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=sub,
            resource_id=rid,
            resource_name="disk1",
            resource_type="compute/disk",
            resource_group="rg",
            location="eastus",
            is_active=True,
        )
    )
    disk_model = get_enrichment_model("compute/disk")
    db_session.add(
        disk_model(
            id=str(uuid.uuid4()),
            subscription_id=sub,
            resource_id=db_session.query(ResourceSnapshot).one().id,
            arm_id=rid,
            snapshot_json=json.dumps(snapshot),
            pipeline_stage="quality_scored",
        )
    )
    db_session.add(
        ResourceAssessmentResult(
            id=str(uuid.uuid4()),
            subscription_id=sub,
            resource_id=rid,
            resource_type="Microsoft.Compute/disks",
            assessment_file="disk-assessment.json",
            score=60.0,
            classification="warning",
            data_quality_json="{}",
            assessed_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    fake_finding = {
        "rule_id": "disk_delete_unattached",
        "resource_id": rid,
        "subscription_id": sub,
        "estimated_savings_usd": 20.0,
        "severity": "HIGH",
        "detail": "Delete unattached disk",
        "recommendation": "Delete unattached disk",
        "evidence": {"rule_source": "rule_engine", "rule_id": "disk_delete_unattached"},
    }

    with (
        patch("app.workers.legacy_engine_worker.run_engine_on_buckets") as run_engine,
        patch("app.workers.legacy_engine_worker.persist_optimization_run", return_value="run-1") as persist,
        patch("app.workers.legacy_engine_worker.load_inventory_from_db", return_value=({}, {}, {})),
        patch("app.workers.legacy_engine_worker.load_cost_by_resource_from_db", return_value={}),
        patch("app.workers.legacy_engine_worker.load_budgets_from_db", return_value={}),
        patch("app.workers.legacy_engine_worker.load_pipeline_resource_facts", return_value={}),
        patch("app.workers.legacy_engine_worker.load_cached_resource_facts", return_value={}),
    ):
        run_engine.return_value = {
            "findings": [fake_finding],
            "summary": {},
            "metrics_context": {},
        }
        result = run_recommendation_worker(db_session, sub)

    assert result["status"] == "ok"
    assert result["findings"] >= 1
    persist.assert_called_once()
    findings = persist.call_args.kwargs["result"]["findings"]
    rule_ids = {f["rule_id"] for f in findings}
    assert "disk_delete_unattached" in rule_ids

    disk_model = get_enrichment_model("compute/disk")
    snap = (
        db_session.query(disk_model)
        .filter(disk_model.arm_id == rid)
        .one()
    )
    assert snap.pipeline_stage == "recommended"
