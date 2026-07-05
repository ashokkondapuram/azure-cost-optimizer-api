"""Regression: failed analysis must not resolve open findings without a successful persist."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.analysis.orchestrator import run_db_analysis
from app.batch_analyzer import create_analysis_job, execute_batch_job
from app.database import SessionLocal, init_db
from app.models import AnalysisJob, OptimizationFinding


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_analysis_persists_without_pre_close(db):
    """Open findings are upserted in persist_optimization_run, not bulk-closed first."""
    call_order: list[str] = []

    def fake_engine(*args, **kwargs):
        call_order.append("engine")
        return {
            "findings": [],
            "summary": {"total_findings": 0, "by_severity": {}},
            "engine_version": "extended",
        }

    def fake_close(*args, **kwargs):
        call_order.append("close")
        return 2

    def fake_persist(*args, **kwargs):
        call_order.append("persist")
        return "run-test"

    with patch("app.analysis.orchestrator.load_inventory_from_db", return_value=({"vms": [{}]}, {"vms": 1}, {})):
        with patch("app.analysis.orchestrator.load_budgets_from_db", return_value=[]):
            with patch("app.analysis.orchestrator.load_cost_by_resource_from_db", return_value={}):
                with patch("app.analysis.orchestrator.load_analysis_metrics", return_value=({}, {}, {}, {}, {})):
                    with patch("app.analysis.orchestrator.run_engine_on_buckets", side_effect=fake_engine):
                        with patch("app.analysis_persist.close_open_findings", side_effect=fake_close):
                            with patch("app.analysis.orchestrator.persist_optimization_run", side_effect=fake_persist):
                                with patch(
                                    "app.analysis.orchestrator.append_cost_export_findings",
                                    side_effect=lambda _db, _sub, r, **_: r,
                                ):
                                    run_db_analysis(db, subscription_id="sub-a", engine_version="extended")

    assert call_order == ["engine", "persist"]
    assert "close" not in call_order


def test_batch_job_failure_rolls_back_resolved_findings(db):
    sub = f"sub-rollback-{uuid.uuid4().hex[:8]}"
    finding_id = str(uuid.uuid4())
    finding = OptimizationFinding(
        id=finding_id,
        run_id="run-old",
        rule_id="VM_IDLE",
        rule_name="Idle VM",
        category="COMPUTE",
        severity="HIGH",
        resource_id="/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        resource_name="vm1",
        resource_type="compute/vm",
        subscription_id=sub,
        resource_group="rg",
        location="eastus",
        detail="idle",
        recommendation="stop",
        status="open",
    )
    db.add(finding)
    db.commit()
    job = create_analysis_job(db, subscription_id=sub, engine_version="extended")
    job_id = job.id
    db.close()

    with patch("app.batch_analyzer.run_db_analysis", side_effect=RuntimeError("engine boom")):
        execute_batch_job(job_id)

    verify = SessionLocal()
    try:
        row = verify.query(OptimizationFinding).filter(OptimizationFinding.id == finding_id).first()
        assert row is not None
        assert row.status == "open"

        refreshed_job = verify.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        assert refreshed_job.status == "failed"
    finally:
        verify.close()
