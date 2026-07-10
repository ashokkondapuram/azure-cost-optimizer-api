"""Cost explorer worker — subscription list and background sync."""

from unittest.mock import MagicMock, patch

from app.cost_explorer_worker import (
    list_cost_sync_subscription_ids,
    request_cost_sync,
)


@patch("app.cost_explorer_worker.cost_explorer_worker_enabled", return_value=True)
@patch("app.subscription_store._default_subscription_from_settings", return_value="default-sub-id")
@patch("app.subscription_store.list_subscriptions_db")
def test_list_cost_sync_subscription_ids_includes_default(mock_list, _mock_default, _enabled):
    mock_list.return_value = [
        {"subscriptionId": "cached-sub", "displayName": "Cached"},
    ]
    db = MagicMock()
    subs = list_cost_sync_subscription_ids(db)
    assert subs == ["cached-sub", "default-sub-id"]


@patch("app.cost_explorer_worker.cost_explorer_worker_enabled", return_value=True)
@patch("app.cost_explorer_worker.threading.Thread")
def test_request_cost_sync_deduplicates(mock_thread, _enabled):
    mock_thread.return_value = MagicMock()
    assert request_cost_sync("aaa-bbb-ccc", reason="test") is True
    assert request_cost_sync("aaa-bbb-ccc", reason="test") is False
    mock_thread.assert_called_once()


@patch("app.cost_explorer_worker.cost_explorer_worker_enabled", return_value=False)
def test_request_cost_sync_disabled(_enabled):
    assert request_cost_sync("aaa-bbb-ccc") is False
