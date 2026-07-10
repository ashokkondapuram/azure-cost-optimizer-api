"""Tests for batched Cost Explorer live queries."""

from unittest.mock import MagicMock, patch

from app.cost_live_query import query_cost_explorer_period_live


def test_explorer_period_live_uses_two_api_calls_not_three():
    daily_resp = {
        "billing_currency": "CAD",
        "properties": {
            "columns": [{"name": "PreTaxCost"}, {"name": "CostUSD"}, {"name": "UsageDate"}, {"name": "Currency"}],
            "rows": [[10.0, 8.0, "20260701", "CAD"]],
        },
    }
    svc_resp = {
        "billing_currency": "CAD",
        "properties": {
            "columns": [{"name": "ServiceName"}, {"name": "PreTaxCost"}, {"name": "CostUSD"}, {"name": "Currency"}],
            "rows": [["Virtual Machines", 10.0, 8.0, "CAD"]],
        },
    }
    client = MagicMock()
    client.query_cost_daily_subscription.return_value = daily_resp
    client.query_cost_by_service.return_value = svc_resp

    with patch("app.cost_live_query.cached_cost_live_query", side_effect=lambda *args, **kwargs: args[3]()):
        with patch("app.cost_live_query.AzureCostClient", return_value=client):
            with patch("app.cost_live_query.arm_patient_sync"):
                with patch("app.auth.arm_auth_context"):
                    result = query_cost_explorer_period_live(
                        MagicMock(),
                        "00000000-0000-0000-0000-000000000001",
                        "MonthToDate",
                        token="token",
                    )

    assert result is not None
    assert result["source"] == "azure"
    assert result["daily"]["properties"]["rows"]
    assert result["by_service"]["properties"]["rows"]
    assert result["summary"]["pretax_total"] == 10.0
    client.query_cost_daily_subscription.assert_called_once()
    client.query_cost_by_service.assert_called_once()
    assert client.query_subscription_totals.call_count == 0
