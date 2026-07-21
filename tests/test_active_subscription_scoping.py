"""Default subscription scoping for workers and schedulers."""

from unittest.mock import MagicMock, patch

from app.scheduler_utils import list_subscription_ids
from app.subscription_store import (
    get_default_subscription_id,
    list_active_subscription_ids,
    subscriptions_list_payload,
)


@patch("app.subscription_store.get_effective_config", create=True)
def test_list_active_subscription_ids_single_mode(mock_cfg):
    mock_cfg.return_value = {"default_subscription_id": "11111111-1111-1111-1111-111111111111"}
    db = MagicMock()
    with patch("app.subscription_store.get_effective_config", mock_cfg):
        with patch("app.services.system_settings.get_effective_config", mock_cfg):
            ids = list_active_subscription_ids(db)
    assert ids == ["11111111-1111-1111-1111-111111111111"]


@patch("app.subscription_store._distinct_subscription_ids", return_value={"aaa-bbb", "ccc-ddd"})
@patch("app.subscription_store.get_default_subscription_id", return_value=None)
def test_list_active_subscription_ids_all_known(_mock_default, _mock_distinct):
    db = MagicMock()
    ids = list_active_subscription_ids(db)
    assert ids == ["aaa-bbb", "ccc-ddd"]


@patch("app.subscription_store.list_active_subscription_ids", return_value=["default-only"])
def test_scheduler_list_subscription_ids_uses_active_scope(mock_active):
    db = MagicMock()
    assert list_subscription_ids(db) == ["default-only"]
    mock_active.assert_called_once_with(db)


@patch("app.subscription_store.list_subscriptions_db")
@patch("app.subscription_store.get_default_subscription_id", return_value="def-sub")
def test_subscriptions_list_payload_includes_default(mock_default, mock_list):
    mock_list.return_value = [
        {"subscriptionId": "def-sub", "displayName": "Primary", "state": "Enabled"},
        {"subscriptionId": "other-sub", "displayName": "Other", "state": "Enabled"},
    ]
    payload = subscriptions_list_payload(MagicMock())
    assert payload["default_subscription_id"] == "def-sub"
    assert payload["subscriptions"][0]["isDefault"] is True
    assert payload["subscriptions"][1].get("isDefault") is not True
