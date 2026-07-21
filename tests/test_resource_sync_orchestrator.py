"""Tests for resource sync enrichment orchestrator."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data_store.enrichment_registry import ensure_enrichment_table, get_enrichment_model
from app.data_store.resource_enrichment import load_enrichment_dict
from app.models import AdvisorRecommendation, Base, ResourceSnapshot
from app.sync.resource_sync_orchestrator import (
    SyncStages,
    queue_subscription_enrichment_after_sync,
    sync_resource_full,
    sync_subscription_full,
)

SUB = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ARM = f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"


@pytest.fixture()
def db_session(monkeypatch):
    monkeypatch.setenv("SYNC_ENRICH_ENABLED", "true")
    monkeypatch.setenv("SYNC_ENRICH_ASYNC", "false")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    ensure_enrichment_table(engine, "compute/vm")
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _snapshot(**overrides) -> ResourceSnapshot:
    now = datetime.now(timezone.utc)
    data = {
        "id": str(uuid.uuid4()),
        "subscription_id": SUB,
        "resource_id": ARM,
        "resource_name": "vm1",
        "resource_type": "compute/vm",
        "resource_group": "rg",
        "location": "eastus",
        "properties_json": '{"provisioningState":"Succeeded"}',
        "tags_json": "{}",
        "sku_json": "{}",
        "monthly_cost_usd": 42.5,
        "monthly_cost_billing": 55.0,
        "billing_currency": "CAD",
        "is_active": True,
        "synced_at": now,
        "analysis_summary_json": json.dumps([
            {
                "rule_id": "VM_IDLE",
                "rule_name": "Idle VM",
                "severity": "MEDIUM",
                "recommendation": "Stop or resize",
                "estimated_savings_usd": 25.0,
            }
        ]),
        "analysis_findings_count": 1,
        "analysis_savings_usd": 25.0,
        "analysis_top_severity": "MEDIUM",
        "analysis_updated_at": now,
    }
    data.update(overrides)
    return ResourceSnapshot(**data)


def test_sync_resource_full_runs_stages_in_order(db_session, monkeypatch):
    monkeypatch.setenv("SYNC_ENRICH_COST", "true")
    monkeypatch.setenv("SYNC_ENRICH_METRICS", "true")
    monkeypatch.setenv("SYNC_ENRICH_ADVISORS", "true")
    monkeypatch.setenv("SYNC_ENRICH_ANALYSIS", "true")

    snap = _snapshot()
    db_session.add(snap)
    db_session.add(
        AdvisorRecommendation(
            id=str(uuid.uuid4()),
            recommendation_id="rec-1",
            resource_id=ARM,
            subscription_id=SUB,
            category="Cost",
            impact="Medium",
            summary="Resize VM",
            description="Resize to save",
            potential_savings_monthly=25.0,
            potential_savings_yearly=300.0,
            status="Active",
            generated_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    order: list[str] = []

    def _properties(db, sub, snapshot):
        order.append("properties")
        from app.data_store.resource_enrichment import upsert_properties

        upsert_properties(db, snapshot)
        return {"status": "ok"}

    def _cost(db, sub, snapshot):
        order.append("cost")
        from app.data_store.resource_enrichment import upsert_cost

        upsert_cost(db, snapshot)
        return {"status": "ok"}

    def _metrics(db, sub, snapshot, *, token):
        order.append("metrics")
        from app.data_store.resource_enrichment import upsert_metrics

        upsert_metrics(db, snapshot, {"cpu_pct": 12.5})
        return {"status": "ok", "ok": True}

    def _advisors(db, sub, snapshot, *, token):
        order.append("advisors")
        from app.data_store.resource_enrichment import upsert_advisor_enrichment

        upsert_advisor_enrichment(db, snapshot, advisor_items=[{"summary": "Resize VM"}])
        return {"status": "ok", "advisor_count": 1}

    def _analysis(db, sub, snapshot):
        order.append("analysis")
        from app.data_store.resource_enrichment import upsert_recommendations

        upsert_recommendations(
            db,
            snapshot,
            summary=[{"rule_id": "VM_IDLE", "severity": "MEDIUM"}],
            findings_count=1,
            savings_usd=25.0,
            top_severity="MEDIUM",
        )
        return {"status": "ok"}

    with (
        patch("app.sync.resource_sync_orchestrator._stage_properties", side_effect=_properties),
        patch("app.sync.resource_sync_orchestrator._stage_cost", side_effect=_cost),
        patch("app.sync.resource_sync_orchestrator._stage_metrics", side_effect=_metrics),
        patch("app.sync.resource_sync_orchestrator._stage_advisors", side_effect=_advisors),
        patch("app.sync.resource_sync_orchestrator._stage_analysis", side_effect=_analysis),
    ):
        result = sync_resource_full(db_session, SUB, resource_id=ARM)

    assert result["status"] == "ok"
    assert order == ["properties", "cost", "metrics", "advisors", "analysis"]

    model = get_enrichment_model("compute/vm")
    row = db_session.query(model).filter(model.arm_id == ARM.lower()).one()
    payload = load_enrichment_dict(row, canonical_type="compute/vm")
    assert payload["properties"]
    assert payload["metrics"]["cpu_pct"] == 12.5
    assert payload["cost"]["monthly_cost_usd"] == 42.5
    assert payload["recommendations"]["advisor_count"] == 1
    assert payload["recommendations"]["summary"][0]["rule_id"] == "VM_IDLE"


def test_sync_subscription_full_respects_disabled_stages(db_session, monkeypatch):
    monkeypatch.setenv("SYNC_ENRICH_COST", "false")
    monkeypatch.setenv("SYNC_ENRICH_METRICS", "false")
    monkeypatch.setenv("SYNC_ENRICH_ADVISORS", "false")
    monkeypatch.setenv("SYNC_ENRICH_ANALYSIS", "false")

    snap = _snapshot()
    db_session.add(snap)
    db_session.commit()

    with (
        patch("app.sync.resource_sync_orchestrator.sync_cost_for_subscription") as cost_mock,
        patch(
            "app.workers.inventory_metrics_worker.run_inventory_metrics_worker",
        ) as metrics_mock,
        patch(
            "app.sync.resource_sync_orchestrator.sync_advisor_enrichment_for_subscription",
        ) as advisor_mock,
        patch("app.analysis.run_db_analysis") as analysis_mock,
    ):
        result = sync_subscription_full(db_session, SUB)

    assert result["status"] == "ok"
    assert "properties" in result["stages"]
    cost_mock.assert_not_called()
    metrics_mock.assert_not_called()
    advisor_mock.assert_not_called()
    analysis_mock.assert_not_called()


def test_queue_subscription_enrichment_async(db_session, monkeypatch):
    monkeypatch.setenv("SYNC_ENRICH_ASYNC", "true")

    with patch("app.sync.resource_sync_orchestrator.threading.Thread") as thread_mock:
        thread_mock.return_value.start = lambda: None
        queued = queue_subscription_enrichment_after_sync(db_session, SUB, token="tok")

    assert queued["status"] == "queued"
    assert queued["async"] is True
    thread_mock.assert_called_once()


def test_sync_stages_from_env(monkeypatch):
    monkeypatch.setenv("SYNC_ENRICH_COST", "false")
    monkeypatch.setenv("SYNC_ENRICH_METRICS", "true")
    monkeypatch.setenv("SYNC_ENRICH_ADVISORS", "no")
    monkeypatch.setenv("SYNC_ENRICH_ANALYSIS", "0")

    stages = SyncStages.from_env()
    assert stages.properties is True
    assert stages.cost is False
    assert stages.metrics is True
    assert stages.advisors is False
    assert stages.analysis is False
