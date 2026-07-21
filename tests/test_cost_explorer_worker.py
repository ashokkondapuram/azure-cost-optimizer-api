"""Cost explorer worker — subscription list and background sync."""

from unittest.mock import MagicMock, patch

from app.cost_explorer_worker import (
    list_cost_sync_subscription_ids,
    request_cost_sync,
)


@patch("app.cost_explorer_worker.cost_explorer_worker_enabled", return_value=True)
@patch("app.subscription_store.list_active_subscription_ids", return_value=["default-sub-id"])
def test_list_cost_sync_subscription_ids_scoped_to_default(_mock_active, _enabled):
    db = MagicMock()
    subs = list_cost_sync_subscription_ids(db)
    assert subs == ["default-sub-id"]


@patch("app.cost_explorer_worker.cost_explorer_worker_enabled", return_value=True)
@patch("app.cost_explorer_worker.threading.Thread")
def test_request_cost_sync_deduplicates(mock_thread, _enabled):
    mock_thread.return_value = MagicMock()
    assert request_cost_sync("aaa-bbb-ccc", reason="test") is True
    assert request_cost_sync("aaa-bbb-ccc", reason="test") is False
    mock_thread.assert_called_once()


@patch("app.cost_explorer_worker.cost_explorer_worker_enabled", return_value=False)
@patch("app.cost_explorer_worker.threading.Thread")
def test_request_cost_sync_runs_when_scheduled_worker_disabled(mock_thread, _enabled):
    mock_thread.return_value = MagicMock()
    assert request_cost_sync("ddd-eee-fff", reason="manual") is True
    mock_thread.assert_called_once()
