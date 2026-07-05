"""Tests for background re-analysis after engine rule config changes."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.batch_analyzer import create_analysis_job, queue_rule_config_reanalysis
from app.metrics_loader import load_cached_resource_facts
from app.models import Base, OptimizationFinding, OptimizationRun


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_create_analysis_job_marks_rule_refresh():
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 0
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()

    job = create_analysis_job(
        db,
        subscription_id="sub-a",
        profile="default",
        skip_monitor_fetch=True,
    )
    components = json.loads(job.components_json)
    assert components[0]["skip_monitor_fetch"] is True
    assert components[0]["component"] == "Rule refresh"


def test_load_cached_resource_facts_from_open_findings(db_session):
    db = db_session
    finding = OptimizationFinding(
        id="f1",
        run_id="run-1",
        rule_id="DISK_OVERSIZE_EXTENDED",
        rule_name="Oversized Premium Disk",
        category="COMPUTE",
        severity="LOW",
        resource_id="/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/disks/d1",
        resource_name="d1",
        resource_type="compute/disk",
        subscription_id="sub-a",
        resource_group="rg",
        location="eastus",
        detail="test",
        recommendation="downgrade",
        evidence_json=json.dumps({
            "disk_read_bps": 12.0,
            "disk_write_bps": 8.0,
            "disk_read_iops": 4.0,
            "disk_write_iops": 2.0,
            "data_source": "azure_monitor",
        }),
        status="open",
    )
    db.add(finding)
    db.commit()

    cached = load_cached_resource_facts(db, "sub-a")
    rid = "/subscriptions/sub-a/resourcegroups/rg/providers/microsoft.compute/disks/d1"
    assert rid in cached
    assert cached[rid]["disk_read_bps"] == 12.0
    assert cached[rid]["disk_read_iops"] == 4.0


@patch("app.batch_analyzer.execute_batch_job")
@patch("app.subscription_store.list_subscriptions_db")
def test_queue_rule_config_reanalysis_enqueues_jobs(mock_list_subs, mock_execute, db_session):
    db = db_session
    mock_list_subs.return_value = [{"subscriptionId": "sub-a"}]
    background_tasks = MagicMock()

    result = queue_rule_config_reanalysis(db, background_tasks, profile="default")

    assert result["status"] == "queued"
    assert result["queued_subscriptions"] == ["sub-a"]
    background_tasks.add_task.assert_called_once()
    assert background_tasks.add_task.call_args[0][0] is mock_execute


@patch("app.analysis.orchestrator.load_cached_resource_facts")
@patch("app.analysis.orchestrator.load_analysis_metrics")
@patch("app.analysis.orchestrator.run_engine_on_buckets")
@patch("app.analysis.orchestrator.persist_optimization_run")
@patch("app.analysis.orchestrator.append_cost_export_findings")
@patch("app.analysis.orchestrator.load_inventory_from_db")
@patch("app.analysis.orchestrator.load_cost_by_resource_from_db")
@patch("app.analysis.orchestrator.load_budgets_from_db")
def test_run_db_analysis_skips_azure_fetch_when_requested(
    mock_budgets,
    mock_costs,
    mock_inventory,
    mock_append_cost,
    mock_persist,
    mock_engine,
    mock_metrics,
    mock_cached,
    db_session,
):
    from app.analysis.orchestrator import run_db_analysis

    mock_inventory.return_value = (
        {"disks": [{"id": "/subscriptions/sub-a/.../disks/d1", "properties": {"diskState": "Attached"}}]},
        {"compute/disk": 1},
        {},
    )
    mock_costs.return_value = {}
    mock_budgets.return_value = []
    mock_metrics.return_value = ({}, {}, {}, {}, {})
    mock_cached.return_value = {
        "/subscriptions/sub-a/.../disks/d1": {"disk_read_bps": 5.0},
    }
    mock_engine.return_value = {"findings": [], "summary": {"total_findings": 0, "by_severity": {}}}
    mock_append_cost.side_effect = lambda _db, _sub, result, **_: result
    mock_persist.return_value = "run-xyz"

    result = run_db_analysis(
        db_session,
        subscription_id="sub-a",
        fetch_monitor_metrics=False,
        include_ai=False,
    )

    mock_metrics.assert_called_once()
    assert mock_metrics.call_args.kwargs["fetch_monitor_metrics"] is False
    mock_cached.assert_called_once()
    assert result["analysis_trigger"] == "rule_config"
    assert "no Azure fetch" in result["coverage_note"]
