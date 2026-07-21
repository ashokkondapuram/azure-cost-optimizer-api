"""Tests for background metrics sync worker."""

from unittest.mock import MagicMock, patch


@patch("app.workers.inventory_metrics_worker.run_inventory_metrics_worker")
@patch("app.metrics_sync_worker._list_subscription_ids")
@patch("app.database.SessionLocal")
def test_metrics_sync_worker_uses_sync_context(mock_session_local, mock_list_subs, mock_run):
    from app.metrics_sync_worker import _refresh_once

    db = MagicMock()
    mock_session_local.return_value = db
    mock_list_subs.return_value = ["sub-1", "sub-2"]
    mock_run.side_effect = [
        {"status": "partial", "metrics_failed": 2, "metrics_loaded": 10},
        {"status": "ok", "metrics_failed": 0, "metrics_loaded": 5},
    ]

    _refresh_once()

    assert mock_run.call_count == 2
    for call in mock_run.call_args_list:
        assert call.args[1] in {"sub-1", "sub-2"}
        assert call.kwargs.get("sync_context") is True


@patch("app.workers.inventory_metrics_worker.run_inventory_metrics_worker")
@patch("app.metrics_sync_worker._list_subscription_ids")
@patch("app.database.SessionLocal")
def test_metrics_sync_worker_completes_with_partial_failures(
    mock_session_local,
    mock_list_subs,
    mock_run,
):
    from app.metrics_sync_worker import _refresh_once, worker_status

    db = MagicMock()
    mock_session_local.return_value = db
    mock_list_subs.return_value = ["sub-1"]
    mock_run.side_effect = Exception("subscription failed")

    _refresh_once()

    status = worker_status()
    assert status["last_result"]["errors"]
    assert status["last_result"]["subscriptions"] == []
