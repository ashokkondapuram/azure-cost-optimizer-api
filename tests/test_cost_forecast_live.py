"""Tests for Azure Cost Management forecast live queries."""

from unittest.mock import MagicMock, patch

from app.azure_cost import monthly_subscription_rows_from_response
from app.cost_live_query import query_demand_forecast_live


def test_monthly_subscription_rows_from_response_groups_by_month():
    response = {
        "properties": {
            "columns": [
                {"name": "PreTaxCost"},
                {"name": "CostUSD"},
                {"name": "BillingMonth"},
                {"name": "Currency"},
            ],
            "rows": [
                [100.0, 80.0, "20250101", "CAD"],
                [50.0, 40.0, "20250201", "CAD"],
            ],
        },
        "billing_currency": "CAD",
    }
    rows = monthly_subscription_rows_from_response(response)
    assert len(rows) == 2
    assert rows[0]["month"] == "2025-01"
    assert rows[0]["total_spend"] == 100.0
    assert rows[1]["month"] == "2025-02"
    assert rows[1]["total_spend"] == 50.0


@patch("app.cost_live_query.query_forecast_daily_live")
@patch("app.cost_live_query.query_forecast_summary_live")
@patch("app.cost_live_query.query_monthly_history_live")
def test_query_demand_forecast_live_combines_azure_sources(mock_history, mock_summary, mock_daily):
    mock_history.return_value = {
        "timeline": [
            {"month": "2025-05", "total_spend": 900.0, "currency": "CAD"},
            {"month": "2026-07", "total_spend": 400.0, "currency": "CAD"},
        ],
        "billing_currency": "CAD",
        "source": "azure",
    }
    mock_summary.return_value = {
        "pretax_total": 1200.0,
        "billing_currency": "CAD",
        "source": "azure",
    }
    mock_daily.return_value = {
        "points": [{"date": "2026-07-07", "cost_billing": 55.0, "currency": "CAD"}],
        "source": "azure",
    }

    payload = query_demand_forecast_live(MagicMock(), "sub-1", months_back=6, token="tok")

    assert payload["source"] == "azure"
    assert payload["forecast_source"] == "azure_cost_management"
    assert payload["projected_month_end"] == 1200.0
    assert len(payload["forecast"]) == 1
    assert payload["forecast"][0]["predicted_spend"] == 1200.0
    assert payload["forecast_daily"][0]["cost_billing"] == 55.0
    assert payload["delta_vs_last_month"] == 800.0
