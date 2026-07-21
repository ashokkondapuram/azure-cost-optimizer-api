"""Tests for unified metrics API response shaping."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.metrics_api import (
    fetch_metrics_for_resource,
    plan_for_resource,
)
from app.metrics_catalog import sql_server_metrics_unavailable


def test_plan_for_sql_server_returns_unavailable():
    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Sql/servers/srv1"
    result = plan_for_resource(rid)
    assert result["ok"] is False
    assert result["data_quality"] == "unavailable"


SNAPSHOT_RID = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/snapshots/s1"


def test_plan_for_resource_no_monitor_profile():
    result = plan_for_resource(SNAPSHOT_RID)
    assert result["ok"] is False
    assert result["data_quality"] == "unavailable"


def test_fetch_metrics_no_monitor_profile_returns_cost_baseline():
    """Snapshots have no Monitor profile but still expose cost-driver context."""
    result = fetch_metrics_for_resource(SNAPSHOT_RID)
    assert result["ok"] is True
    assert result["data_quality"] == "inventory"
    assert result["canonical_type"] == "compute/snapshot"
    assert result["cost_driver_mapping"]["cost_drivers"]


@patch("app.azure_resources.AzureResourcesClient")
@patch("app.auth.arm_auth_context")
@patch("app.auth.get_token")
def test_fetch_metrics_unified_shape(mock_token, mock_auth, mock_client_cls):
    mock_token.return_value = "token"
    mock_auth.return_value.__enter__ = MagicMock(return_value=None)
    mock_auth.return_value.__exit__ = MagicMock(return_value=None)
    client = MagicMock()
    mock_client_cls.return_value = client
    client.get_resource_metrics.return_value = {
        "value": [{
            "name": {"value": "Percentage CPU"},
            "timeseries": [{"data": [{"average": 12.5, "maximum": 20.0, "minimum": 5.0}]}],
        }],
    }

    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
    result = fetch_metrics_for_resource(rid, db=MagicMock())

    assert result["ok"] is True
    assert result["data_quality"] == "azure_monitor"
    assert isinstance(result["metrics"], list)
    assert result["metrics"][0]["fact_key"] == "avg_cpu_pct"
    assert "trigger" in result["metrics"][0]
    assert isinstance(result["derived"], list)


def test_sql_unavailable_helpers_agree():
    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Sql/servers/srv1"
    assert sql_server_metrics_unavailable(rid) is not None
