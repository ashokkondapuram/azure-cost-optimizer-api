"""Tests for unified sync orchestrator."""

import threading
import time
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.sync_orchestrator import (
    STAGE_ORDER,
    assert_inventory_persisted,
    cancel_full_sync_pipeline,
    expire_stale_pipeline_runs,
    get_pipeline_status,
    is_full_sync_pending,
    request_full_sync,
    reset_full_sync_pipeline,
)


SUBSCRIPTION_ID = str(uuid.uuid4()).lower()


def _mock_db_session(*, job_status="completed", error_message=None):
    class _Session:
        def close(self):
            return None

        def rollback(self):
            return None

        def commit(self):
            return None

        def query(self, _model):
            return _JobQuery()

    class _JobQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def order_by(self, *_args, **_kwargs):
            return self

        def first(self):
            job = MagicMock()
            job.status = job_status
            job.error_message = error_message
            return job

        def all(self):
            return []

    return _Session()


@pytest.fixture(autouse=True)
def _reset_orchestrator_state():
    import app.sync_orchestrator as module

    with module._lock:
        module._pending.clear()
        module._pipeline_by_sub.clear()
    yield
    with module._lock:
        module._pending.clear()
        module._pipeline_by_sub.clear()


@pytest.fixture(autouse=True)
def _inmemory_pipeline_db(monkeypatch):
    """Avoid real DB writes during orchestrator unit tests."""
    import copy

    store: dict[str, dict] = {}

    def fake_persist(state):
        sub = (state.get("subscription_id") or "").strip().lower()
        pipeline_id = state.get("pipeline_id")
        if sub and pipeline_id:
            store[pipeline_id] = copy.deepcopy(state)
            for key, row in list(store.items()):
                if key != pipeline_id and (row.get("subscription_id") or "").lower() == sub:
                    if row.get("status") in {"queued", "running"} and state.get("status") in {"queued", "running", "running"}:
                        if row.get("pipeline_id") != pipeline_id:
                            row["status"] = "failed"
                            row["error"] = state.get("error") or "Superseded"
                            store[key] = row

    def fake_load(sub):
        from app.sync_orchestrator import _now

        sub_key = (sub or "").strip().lower()
        matches = [
            row for row in store.values()
            if (row.get("subscription_id") or "").lower() == sub_key
        ]
        if not matches:
            return None
        matches.sort(key=lambda row: row.get("created_at") or _now(), reverse=True)
        return copy.deepcopy(matches[0])

    def fake_row_active(sub, pipeline_id):
        row = store.get(pipeline_id)
        return bool(row and row.get("status") in {"queued", "running"})

    monkeypatch.setattr("app.sync_orchestrator._persist_pipeline_state", fake_persist)
    monkeypatch.setattr("app.sync_orchestrator._load_pipeline_from_db", fake_load)
    monkeypatch.setattr("app.sync_orchestrator._pipeline_row_still_active", fake_row_active)
    yield store


def test_request_full_sync_returns_accepted_immediately():
    with patch("app.sync_orchestrator.threading.Thread") as thread_cls:
        thread_cls.return_value = MagicMock()
        enqueued, payload = request_full_sync(SUBSCRIPTION_ID, reason="test")

    assert enqueued is True
    assert payload["status"] == "accepted"
    assert payload["async"] is True
    assert payload["pipeline"]["subscription_id"] == SUBSCRIPTION_ID
    assert payload["pipeline"]["status"] in {"queued", "running"}
    thread_cls.assert_called_once()


def test_request_full_sync_deduplicates():
    with patch("app.sync_orchestrator.threading.Thread") as thread_cls:
        thread_cls.return_value = MagicMock()
        first_ok, first = request_full_sync(SUBSCRIPTION_ID, reason="test")
        second_ok, second = request_full_sync(SUBSCRIPTION_ID, reason="test")

    assert first_ok is True
    assert second_ok is False
    assert second["already_queued"] is True
    assert second.get("pipeline_id")
    assert second.get("reason") == "already_running"
    assert second["pipeline"] is not None
    assert thread_cls.call_count == 1


def test_pipeline_runs_stages_in_order(monkeypatch):
    call_order: list[str] = []

    def _inventory(*_args, **_kwargs):
        call_order.append("inventory")
        return {"resources": {"compute/vm": 2}, "db_total": 2}

    def _cost(*_args, **_kwargs):
        call_order.append("cost")
        return {"status": "ok"}

    def _metrics(*_args, **_kwargs):
        call_order.append("metrics")
        return {"resources_processed": 2}

    def _create_job(db, **kwargs):
        call_order.append("analysis_create")
        job = MagicMock()
        job.id = "job-123"
        job.status = "completed"
        return job

    def _execute(job_id):
        call_order.append(f"analysis_execute:{job_id}")

    monkeypatch.setattr("app.auth.get_token", lambda _db: "token")
    monkeypatch.setattr("app.db_sync.sync_all", _inventory)
    monkeypatch.setattr("app.cost_explorer_sync.sync_cost_explorer", _cost)
    monkeypatch.setattr("app.workers.inventory_metrics_worker.run_inventory_metrics_worker", _metrics)
    monkeypatch.setattr("app.batch_analyzer.create_analysis_job", _create_job)
    monkeypatch.setattr("app.batch_analyzer.execute_batch_job", _execute)

    monkeypatch.setattr("app.database.SessionLocal", lambda: _mock_db_session())

    request_full_sync(SUBSCRIPTION_ID, reason="test")

    deadline = time.time() + 3.0
    pipeline = None
    while time.time() < deadline:
        pipeline = get_pipeline_status(SUBSCRIPTION_ID)
        if pipeline and pipeline["status"] == "completed":
            break
        time.sleep(0.05)

    assert call_order == [
        "inventory",
        "cost",
        "metrics",
        "analysis_create",
        "analysis_execute:job-123",
    ]
    assert pipeline is not None
    assert pipeline["status"] == "completed"
    assert pipeline["progress_pct"] == 100
    for stage in STAGE_ORDER:
        assert pipeline["stages"][stage]["status"] in {"done", "skipped"}
    assert not is_full_sync_pending(SUBSCRIPTION_ID)


def test_pipeline_failure_marks_stage_failed(monkeypatch):
    def _inventory(*_args, **_kwargs):
        raise RuntimeError("inventory boom")

    monkeypatch.setattr("app.auth.get_token", lambda _db: "token")
    monkeypatch.setattr("app.db_sync.sync_all", _inventory)

    monkeypatch.setattr("app.database.SessionLocal", lambda: _mock_db_session())

    request_full_sync(SUBSCRIPTION_ID, reason="test")

    deadline = time.time() + 3.0
    pipeline = None
    while time.time() < deadline:
        pipeline = get_pipeline_status(SUBSCRIPTION_ID)
        if pipeline and pipeline["status"] == "failed":
            break
        time.sleep(0.05)

    assert pipeline is not None
    assert pipeline["status"] == "failed"
    assert pipeline["stages"]["inventory"]["status"] == "failed"
    assert "inventory boom" in (pipeline["error"] or "")


def test_assert_inventory_persisted_raises_on_empty_db():
    with pytest.raises(RuntimeError, match="No resources were saved"):
        assert_inventory_persisted({"resources": {}, "db_total": 0}, scoped=False)


def test_assert_inventory_persisted_raises_on_commit_mismatch():
    with pytest.raises(RuntimeError, match="none were saved to the database"):
        assert_inventory_persisted({"resources": {"compute/vm": 3}, "db_total": 0}, scoped=False)


def test_serialize_pipeline_includes_stage_results():
    from app.sync_orchestrator import _serialize_pipeline

    state = {
        "pipeline_id": "pipe-1",
        "subscription_id": "sub-a",
        "status": "completed",
        "current_stage": "completed",
        "progress_pct": 100,
        "stages": {
            "inventory": {
                "status": "done",
                "started_at": None,
                "completed_at": None,
                "error": None,
                "result": {"db_total": 12, "resources": {"compute/vm": 12}},
            },
            "cost": {"status": "done", "started_at": None, "completed_at": None, "error": None},
            "metrics": {"status": "done", "started_at": None, "completed_at": None, "error": None},
            "analysis": {"status": "done", "started_at": None, "completed_at": None, "error": None},
        },
        "analysis_job_id": "job-1",
        "started_at": None,
        "completed_at": None,
        "error": None,
    }
    payload = _serialize_pipeline(state)
    assert payload["stages"]["inventory"]["result"]["db_total"] == 12


def test_pipeline_fails_when_inventory_persists_nothing(monkeypatch):
    def _inventory(*_args, **_kwargs):
        return {"resources": {}, "db_total": 0}

    monkeypatch.setattr("app.auth.get_token", lambda _db: "token")
    monkeypatch.setattr("app.db_sync.sync_all", _inventory)

    monkeypatch.setattr("app.database.SessionLocal", lambda: _mock_db_session())

    request_full_sync(SUBSCRIPTION_ID, reason="test")

    deadline = time.time() + 3.0
    pipeline = None
    while time.time() < deadline:
        pipeline = get_pipeline_status(SUBSCRIPTION_ID)
        if pipeline and pipeline["status"] == "failed":
            break
        time.sleep(0.05)

    assert pipeline is not None
    assert pipeline["status"] == "failed"
    assert pipeline["stages"]["inventory"]["status"] == "failed"
    assert "No resources were saved" in (pipeline["error"] or "")
    assert pipeline["stages"]["cost"]["status"] == "pending"


def test_cancel_full_sync_pipeline_clears_pending(monkeypatch):
    with patch("app.sync_orchestrator.threading.Thread") as thread_cls:
        thread_cls.return_value = MagicMock()
        request_full_sync(SUBSCRIPTION_ID, reason="cancel-test")

    assert is_full_sync_pending(SUBSCRIPTION_ID)
    result = cancel_full_sync_pipeline(SUBSCRIPTION_ID)
    assert result["status"] == "cancelled"
    assert not is_full_sync_pending(SUBSCRIPTION_ID)


def test_stale_pipeline_reason_detects_old_running():
    from datetime import timedelta

    import app.sync_orchestrator as module

    reason = module._stale_pipeline_reason({
        "status": "running",
        "started_at": module._now() - timedelta(hours=module.full_sync_pipeline_max_runtime_hours() + 1),
    })
    assert reason
    assert "time limit" in reason.lower()


def test_stale_pipeline_reason_ignores_completed():
    import app.sync_orchestrator as module

    assert module._stale_pipeline_reason({"status": "completed"}) is None


def test_request_full_sync_force_restarts_after_cancel(monkeypatch):
    with patch("app.sync_orchestrator.threading.Thread") as thread_cls:
        thread_cls.return_value = MagicMock()
        request_full_sync(SUBSCRIPTION_ID, reason="first")
        cancel_full_sync_pipeline(SUBSCRIPTION_ID)
        ok, payload = request_full_sync(SUBSCRIPTION_ID, reason="second", force=True)

    assert ok is True
    assert payload["already_queued"] is False
    assert thread_cls.call_count == 2


def test_reset_full_sync_pipeline_alias(monkeypatch):
    with patch("app.sync_orchestrator.threading.Thread") as thread_cls:
        thread_cls.return_value = MagicMock()
        request_full_sync(SUBSCRIPTION_ID, reason="reset-test")

    payload = reset_full_sync_pipeline(SUBSCRIPTION_ID)
    assert payload["status"] == "cancelled"
    assert not is_full_sync_pending(SUBSCRIPTION_ID)


def test_pipeline_status_survives_memory_reset():
    with patch("app.sync_orchestrator.threading.Thread") as thread_cls:
        thread_cls.return_value = MagicMock()
        request_full_sync(SUBSCRIPTION_ID, reason="persist-test")

    import app.sync_orchestrator as module

    with module._lock:
        state = module._pipeline_by_sub.get(SUBSCRIPTION_ID)
    assert state is not None
    module._touch_pipeline(state)

    with module._lock:
        module._pipeline_by_sub.clear()

    pipeline = get_pipeline_status(SUBSCRIPTION_ID)
    assert pipeline is not None
    assert pipeline["subscription_id"] == SUBSCRIPTION_ID
    assert pipeline["status"] in {"queued", "running", "completed", "failed"}


def test_orphaned_memory_queued_resumes_on_poll(monkeypatch):
    import app.sync_orchestrator as module

    scoped_calls: list[list[str]] = []

    def _scoped(_sub, _db, _token, types, **kwargs):
        scoped_calls.append(list(types))
        return {"resources": {"network/vnet": 1}, "db_total": 1, "types": types}

    monkeypatch.setattr("app.auth.get_token", lambda _db: "token")
    monkeypatch.setattr("app.db_sync.sync_scoped", _scoped)
    monkeypatch.setattr("app.cost_explorer_sync.sync_cost_explorer", lambda *_a, **_k: {"status": "ok"})
    monkeypatch.setattr("app.workers.inventory_metrics_worker.run_inventory_metrics_worker", lambda *_a, **_k: {"status": "ok"})
    monkeypatch.setattr("app.batch_analyzer.create_analysis_job", lambda db, **kwargs: type("Job", (), {"id": "job-resume", "status": "completed"})())
    monkeypatch.setattr("app.batch_analyzer.execute_batch_job", lambda _job_id: None)
    monkeypatch.setattr("app.database.SessionLocal", lambda: _mock_db_session())

    state = module._new_pipeline_state(SUBSCRIPTION_ID)
    state["run_params"] = {
        "type_list": ["network/vnet"],
        "scope_resource_types": ["network/vnet"],
        "include_costs": False,
        "reason": "orphan-memory",
    }
    module._touch_pipeline(state)
    with module._lock:
        module._pipeline_by_sub[SUBSCRIPTION_ID] = state

    pipeline = get_pipeline_status(SUBSCRIPTION_ID)
    assert pipeline is not None
    assert pipeline["pending"] is True

    deadline = time.time() + 3.0
    while time.time() < deadline:
        pipeline = get_pipeline_status(SUBSCRIPTION_ID)
        if pipeline and pipeline["status"] == "completed":
            break
        time.sleep(0.05)

    assert scoped_calls == [["network/vnet"]]
    assert pipeline["status"] == "completed"


def test_request_full_sync_reaches_running_within_two_seconds(monkeypatch):
    def _inventory(*_args, **_kwargs):
        return {"resources": {"compute/vm": 1}, "db_total": 1}

    monkeypatch.setattr("app.auth.get_token", lambda _db: "token")
    monkeypatch.setattr("app.db_sync.sync_all", _inventory)
    monkeypatch.setattr("app.cost_explorer_sync.sync_cost_explorer", lambda *_a, **_k: {"status": "ok"})
    monkeypatch.setattr("app.workers.inventory_metrics_worker.run_inventory_metrics_worker", lambda *_a, **_k: {"status": "ok"})
    monkeypatch.setattr("app.batch_analyzer.create_analysis_job", lambda db, **kwargs: type("Job", (), {"id": "job-fast", "status": "completed"})())
    monkeypatch.setattr("app.batch_analyzer.execute_batch_job", lambda _job_id: None)
    monkeypatch.setattr("app.database.SessionLocal", lambda: _mock_db_session())

    request_full_sync(SUBSCRIPTION_ID, reason="fast-running")

    deadline = time.time() + 2.0
    pipeline = None
    saw_running = False
    while time.time() < deadline:
        pipeline = get_pipeline_status(SUBSCRIPTION_ID)
        if pipeline and pipeline["status"] in {"running", "completed"}:
            saw_running = True
            break
        time.sleep(0.05)

    assert saw_running, f"pipeline should reach running within 2s, got {pipeline}"


def test_request_full_sync_starts_worker_thread():
    with patch("app.sync_orchestrator.threading.Thread") as thread_cls:
        thread_cls.return_value = MagicMock()
        enqueued, payload = request_full_sync(SUBSCRIPTION_ID, reason="thread-test")

    assert enqueued is True
    assert payload["status"] == "accepted"
    thread_cls.assert_called_once()


def test_scoped_sync_runs_sync_scoped(monkeypatch):
    scoped_calls: list[list[str]] = []

    def _scoped(_sub, _db, _token, types, **kwargs):
        scoped_calls.append(list(types))
        return {"resources": {"network/vnet": 2}, "db_total": 2, "types": types}

    monkeypatch.setattr("app.auth.get_token", lambda _db: "token")
    monkeypatch.setattr("app.db_sync.sync_scoped", _scoped)
    monkeypatch.setattr("app.db_sync.sync_all", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("full sync should not run")))
    monkeypatch.setattr("app.cost_explorer_sync.sync_cost_explorer", lambda *_a, **_k: {"status": "ok"})
    monkeypatch.setattr("app.workers.inventory_metrics_worker.run_inventory_metrics_worker", lambda *_a, **_k: {"status": "ok"})
    monkeypatch.setattr("app.batch_analyzer.create_analysis_job", lambda db, **kwargs: type("Job", (), {"id": "job-scoped", "status": "completed"})())
    monkeypatch.setattr("app.batch_analyzer.execute_batch_job", lambda _job_id: None)
    monkeypatch.setattr("app.database.SessionLocal", lambda: _mock_db_session())

    request_full_sync(
        SUBSCRIPTION_ID,
        type_list=["network/vnet"],
        scope_resource_types=["network/vnet"],
        include_costs=False,
        reason="scoped-test",
    )

    deadline = time.time() + 3.0
    pipeline = None
    while time.time() < deadline:
        pipeline = get_pipeline_status(SUBSCRIPTION_ID)
        if pipeline and pipeline["status"] == "completed":
            break
        time.sleep(0.05)

    assert scoped_calls == [["network/vnet"]]
    assert pipeline is not None
    assert pipeline["status"] == "completed"


def test_new_scoped_sync_supersedes_without_worker_inactive_error(monkeypatch):
    import app.sync_orchestrator as module

    stale_state = module._new_pipeline_state(SUBSCRIPTION_ID)
    stale_state["run_params"] = {"type_list": ["network/vnet"], "scope_resource_types": ["network/vnet"]}
    module._mark_pipeline_failed(stale_state, "inventory", "Stale pipeline for supersede test.")

    scoped_calls: list[list[str]] = []

    def _scoped(_sub, _db, _token, types, **kwargs):
        scoped_calls.append(list(types))
        return {"resources": {"compute/disk": 1}, "db_total": 1, "types": types}

    monkeypatch.setattr("app.auth.get_token", lambda _db: "token")
    monkeypatch.setattr("app.db_sync.sync_scoped", _scoped)
    monkeypatch.setattr("app.cost_explorer_sync.sync_cost_explorer", lambda *_a, **_k: {"status": "ok"})
    monkeypatch.setattr("app.workers.inventory_metrics_worker.run_inventory_metrics_worker", lambda *_a, **_k: {"status": "ok"})
    monkeypatch.setattr("app.batch_analyzer.create_analysis_job", lambda db, **kwargs: type("Job", (), {"id": "job-disk", "status": "completed"})())
    monkeypatch.setattr("app.batch_analyzer.execute_batch_job", lambda _job_id: None)
    monkeypatch.setattr("app.database.SessionLocal", lambda: _mock_db_session())

    enqueued, payload = request_full_sync(
        SUBSCRIPTION_ID,
        type_list=["compute/disk"],
        scope_resource_types=["compute/disk"],
        reason="supersede-test",
    )

    assert enqueued is True
    deadline = time.time() + 3.0
    pipeline = None
    while time.time() < deadline:
        pipeline = get_pipeline_status(SUBSCRIPTION_ID)
        if pipeline and pipeline["status"] == "completed":
            break
        time.sleep(0.05)

    assert scoped_calls == [["compute/disk"]]
    assert pipeline is not None
    assert pipeline["status"] == "completed"
    assert "worker is no longer active" not in (pipeline.get("error") or "").lower()


def test_get_pipeline_status_resumes_orphaned_worker(monkeypatch):
    import app.sync_orchestrator as module

    run_params = {
        "token": None,
        "type_list": ["database/cosmosdb"],
        "scope_resource_types": ["database/cosmosdb"],
        "include_costs": False,
        "reason": "resume-test",
        "force": False,
    }
    state = module._new_pipeline_state(SUBSCRIPTION_ID)
    state["run_params"] = run_params
    module._touch_pipeline(state)

    scoped_calls: list[list[str]] = []

    def _scoped(_sub, _db, _token, types, **kwargs):
        scoped_calls.append(list(types))
        return {"resources": {"database/cosmosdb": 1}, "db_total": 1, "types": types}

    monkeypatch.setattr("app.auth.get_token", lambda _db: "token")
    monkeypatch.setattr("app.db_sync.sync_scoped", _scoped)
    monkeypatch.setattr("app.cost_explorer_sync.sync_cost_explorer", lambda *_a, **_k: {"status": "ok"})
    monkeypatch.setattr("app.workers.inventory_metrics_worker.run_inventory_metrics_worker", lambda *_a, **_k: {"status": "ok"})
    monkeypatch.setattr("app.batch_analyzer.create_analysis_job", lambda db, **kwargs: type("Job", (), {"id": "job-cosmos", "status": "completed"})())
    monkeypatch.setattr("app.batch_analyzer.execute_batch_job", lambda _job_id: None)
    monkeypatch.setattr("app.database.SessionLocal", lambda: _mock_db_session())

    pipeline = get_pipeline_status(SUBSCRIPTION_ID)
    assert pipeline is not None

    deadline = time.time() + 3.0
    while time.time() < deadline:
        pipeline = get_pipeline_status(SUBSCRIPTION_ID)
        if pipeline and pipeline["status"] == "completed":
            break
        time.sleep(0.05)

    assert scoped_calls == [["database/cosmosdb"]]
    assert pipeline is not None
    assert pipeline["status"] == "completed"


def test_cosmosdb_scoped_sync_reaches_inventory_start(monkeypatch):
    inventory_started = threading.Event()
    scoped_calls: list[list[str]] = []

    def _scoped(_sub, _db, _token, types, **kwargs):
        scoped_calls.append(list(types))
        inventory_started.set()
        return {"resources": {"database/cosmosdb": 1}, "db_total": 1, "types": types}

    monkeypatch.setattr("app.sync_orchestrator._fetch_worker_token", lambda _db: "token")
    monkeypatch.setattr("app.db_sync.sync_scoped", _scoped)
    monkeypatch.setattr("app.cost_explorer_sync.sync_cost_explorer", lambda *_a, **_k: {"status": "ok"})
    monkeypatch.setattr("app.workers.inventory_metrics_worker.run_inventory_metrics_worker", lambda *_a, **_k: {"status": "ok"})
    monkeypatch.setattr("app.batch_analyzer.create_analysis_job", lambda db, **kwargs: type("Job", (), {"id": "job-cosmos-start", "status": "completed"})())
    monkeypatch.setattr("app.batch_analyzer.execute_batch_job", lambda _job_id: None)
    monkeypatch.setattr("app.database.SessionLocal", lambda: _mock_db_session())

    request_full_sync(
        SUBSCRIPTION_ID,
        type_list=["database/cosmosdb"],
        scope_resource_types=["database/cosmosdb"],
        include_costs=False,
        reason="cosmos-inventory-start",
    )

    assert inventory_started.wait(timeout=3.0), "scoped inventory never started"
    assert scoped_calls == [["database/cosmosdb"]]


def test_worker_stall_allows_retry(monkeypatch):
    import app.sync_orchestrator as module

    monkeypatch.setenv("FULL_SYNC_PIPELINE_WORKER_STALL_SECONDS", "1")

    state = module._new_pipeline_state(SUBSCRIPTION_ID)
    state["run_params"] = {
        "type_list": ["database/cosmosdb"],
        "scope_resource_types": ["database/cosmosdb"],
        "include_costs": False,
        "reason": "stall-test",
        "force": False,
    }
    state["worker_entered_at"] = module._now() - timedelta(seconds=5)
    module._touch_pipeline(state)

    with module._lock:
        module._pending.add(SUBSCRIPTION_ID)
        module._pipeline_by_sub[SUBSCRIPTION_ID] = state

    reason = module._stale_pipeline_reason(state)
    assert reason is not None

    with patch("app.sync_orchestrator.threading.Thread") as thread_cls:
        thread_cls.return_value = MagicMock()
        enqueued, payload = request_full_sync(
            SUBSCRIPTION_ID,
            type_list=["database/cosmosdb"],
            scope_resource_types=["database/cosmosdb"],
            include_costs=False,
            reason="stall-retry",
        )

    assert enqueued is True
    assert payload["status"] == "accepted"
    thread_cls.assert_called_once()
