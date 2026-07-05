"""Tests for memory-safe batch analysis."""

import json
import uuid
from unittest.mock import MagicMock

from app.analysis_summary import summarize_findings
from app.batch_analyzer import (
    create_analysis_job,
    queue_post_sync_analysis,
    serialize_job,
    _execution_scope_from_job,
    _is_scoped_analysis,
)
from app.analysis import BUCKET_TO_TYPES, load_buckets_for_keys


def test_summarize_findings():
    findings = [
        {
            "rule_id": "VM_IDLE",
            "rule_name": "Idle VM",
            "category": "COMPUTE",
            "severity": "HIGH",
            "estimated_savings_usd": 10.0,
            "confidence_score": 80,
        },
        {
            "rule_id": "VM_IDLE",
            "rule_name": "Idle VM",
            "category": "COMPUTE",
            "severity": "MEDIUM",
            "estimated_savings_usd": 5.0,
            "confidence_score": 60,
        },
    ]
    result = summarize_findings(findings, "extended")
    assert result["summary"]["total_findings"] == 2
    assert result["summary"]["total_estimated_monthly_savings_usd"] == 15.0
    assert result["summary"]["by_severity"]["HIGH"] == 1


def test_bucket_to_types_covers_vms():
    assert "compute/vm" in BUCKET_TO_TYPES["vms"]
    assert "compute/vmss" in BUCKET_TO_TYPES["vmss"]


def test_empty_buckets_includes_vmss():
    from app.analysis import empty_buckets

    assert "vmss" in empty_buckets()


def test_load_buckets_for_keys_vmss_no_key_error():
    from app.database import SessionLocal, init_db
    from app.analysis import empty_buckets, load_buckets_for_keys
    from unittest.mock import patch

    init_db()
    db = SessionLocal()
    vmss_row = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/myvmss",
        "name": "myvmss",
        "type": "compute/vmss",
        "resourceGroup": "rg",
        "location": "eastus",
        "sku": "Standard_D2s_v3",
        "state": "Succeeded",
        "tags": {},
        "properties": {"virtualMachineProfile": {"hardwareProfile": {"vmSize": "Standard_D2s_v3"}}},
    }
    try:
        with patch("app.analysis.orchestrator.list_resources_by_types_db", return_value=[vmss_row]):
            buckets, pools = load_buckets_for_keys(db, "test-sub", ["vmss", "vms"])
        assert len(buckets["vmss"]) == 1
        assert buckets["vmss"][0]["name"] == "myvmss"
        assert pools == {}
        assert "vmss" in empty_buckets()
    finally:
        db.close()


def test_load_buckets_for_keys_empty():
    from app.database import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        buckets, pools = load_buckets_for_keys(db, "none-sub", ["vms"])
        assert buckets["vms"] == []
        assert pools == {}
    finally:
        db.close()


def test_queue_post_sync_analysis_always_queues(monkeypatch):
    from app.database import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    tasks = MagicMock()
    try:
        sub = f"test-sub-{uuid.uuid4().hex[:8]}"
        result = queue_post_sync_analysis(
            db,
            tasks,
            subscription_id=sub,
        )
        assert result["status"] == "queued"
        assert result["job_id"]
        tasks.add_task.assert_called_once()
    finally:
        db.close()


def test_queue_post_sync_analysis_queues_job(monkeypatch):
    from app.database import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    tasks = MagicMock()
    try:
        sub = f"test-sub-{uuid.uuid4().hex[:8]}"
        result = queue_post_sync_analysis(
            db,
            tasks,
            subscription_id=sub,
            type_list=["compute/vm"],
        )
        assert result["status"] == "queued"
        assert result["job_id"]
        assert result["scoped"] is True
        tasks.add_task.assert_called_once()
    finally:
        db.close()


def test_queue_post_sync_analysis_scopes_to_canonical_types():
    from app.database import SessionLocal, init_db
    from app.models import AnalysisJob

    init_db()
    db = SessionLocal()
    tasks = MagicMock()
    try:
        sub = f"test-sub-{uuid.uuid4().hex[:8]}"
        result = queue_post_sync_analysis(
            db,
            tasks,
            subscription_id=sub,
            type_list=["network/privateendpoint"],
        )
        assert result["scoped"] is True
        job = db.query(AnalysisJob).filter(AnalysisJob.id == result["job_id"]).first()
        components = json.loads(job.components_json or "[]")
        assert components[0]["scope_resource_types"] == ["network/privateendpoint"]
    finally:
        db.close()


def test_create_analysis_job():
    from app.database import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        sub = f"test-sub-{uuid.uuid4().hex[:8]}"
        job = create_analysis_job(db, subscription_id=sub, engine_version="extended")
        payload = serialize_job(job)
        assert payload["status"] == "queued"
        assert payload["total_batches"] > 0
        assert payload["scope_label"] == "Full analysis"
        assert payload["is_active"] is True
        assert payload["status_label"] == "Queued"
        components = json.loads(job.components_json or "[]")
        assert components[0]["analysis_scope_components"] == []
    finally:
        db.close()


def test_execution_scope_from_full_analysis_job_label():
    from app.models import AnalysisJob

    job = AnalysisJob(
        id="job-full",
        subscription_id="sub-1",
        components_json=json.dumps([{
            "component": "Full analysis",
            "status": "pending",
            "scope_resource_types": [],
        }]),
    )
    scope_components, scope_resource_types, skip_monitor = _execution_scope_from_job(job)
    assert scope_components is None
    assert scope_resource_types == []
    assert skip_monitor is False
    assert _is_scoped_analysis(scope_components, scope_resource_types) is False


def test_execution_scope_from_scoped_component_job():
    from app.models import AnalysisJob

    job = AnalysisJob(
        id="job-vm",
        subscription_id="sub-1",
        components_json=json.dumps([{
            "component": "Virtual Machines",
            "status": "pending",
            "analysis_scope_components": ["Virtual Machines"],
            "scope_resource_types": [],
        }]),
    )
    scope_components, scope_resource_types, skip_monitor = _execution_scope_from_job(job)
    assert scope_components == ["Virtual Machines"]
    assert _is_scoped_analysis(scope_components, scope_resource_types) is True


def test_create_analysis_job_rejects_duplicate_active():
    from app.database import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        sub = f"dup-sub-{uuid.uuid4().hex[:8]}"
        create_analysis_job(db, subscription_id=sub, engine_version="extended")
        try:
            create_analysis_job(db, subscription_id=sub, engine_version="extended")
            assert False, "expected duplicate active job rejection"
        except ValueError as exc:
            assert "in progress" in str(exc).lower()
    finally:
        db.close()
