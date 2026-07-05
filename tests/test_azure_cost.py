"""Tests for Azure Cost Management API client helpers."""

from app.azure_cost import (
    daily_query_to_export_rows,
    merge_query_responses,
    normalize_query_response,
    resource_group_filter,
    resource_type_filter,
)
from app.cost_utils import summarize_cost_response


def test_normalize_query_response_aliases_columns():
    raw = {
        "properties": {
            "columns": [
                {"name": "ResourceGroupName"},
                {"name": "totalCost"},
                {"name": "totalCostUSD"},
            ],
            "rows": [["rg-a", 10.0, 8.0]],
        }
    }
    out = normalize_query_response(raw)
    names = [c["name"] for c in out["properties"]["columns"]]
    assert names == ["ResourceGroup", "PreTaxCost", "CostUSD"]


def test_daily_subscription_rows_from_daily_granularity_response():
    from app.azure_cost import daily_subscription_rows_from_response, normalize_query_response

    response = normalize_query_response({
        "properties": {
            "columns": [
                {"name": "UsageDate"},
                {"name": "PreTaxCost"},
                {"name": "CostUSD"},
                {"name": "Currency"},
            ],
            "rows": [
                ["20250601", 40.0, 32.0, "CAD"],
                ["20250602", 55.5, 44.0, "CAD"],
            ],
        },
        "billing_currency": "CAD",
    })
    rows = daily_subscription_rows_from_response(response)
    assert len(rows) == 2
    assert rows[0]["date"] == "2025-06-01"
    assert rows[0]["cost"] == 40.0
    assert rows[1]["date"] == "2025-06-02"


def test_daily_query_to_export_rows_parses_usage_date():
    response = normalize_query_response({
        "properties": {
            "columns": [
                {"name": "UsageDate"},
                {"name": "ResourceGroupName"},
                {"name": "ServiceName"},
                {"name": "PreTaxCost"},
                {"name": "CostUSD"},
                {"name": "Currency"},
            ],
            "rows": [
                ["20260615", "rg-apps", "Virtual Machines", 120.5, 95.0, "CAD"],
            ],
        },
    })
    rows = daily_query_to_export_rows(response)
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-06-15"
    assert rows[0]["cost"] == 120.5
    assert rows[0]["cost_usd"] == 95.0
    assert rows[0]["currency"] == "CAD"
    assert rows[0]["resource_group"] == "rg-apps"
    assert rows[0]["service_name"] == "Virtual Machines"


def test_daily_query_to_export_rows_does_not_treat_cad_pretax_as_usd():
    """When billing is CAD and CostUSD is absent, do not store PreTaxCost as cost_usd."""
    response = normalize_query_response({
        "properties": {
            "columns": [
                {"name": "UsageDate"},
                {"name": "PreTaxCost"},
                {"name": "CostUSD"},
                {"name": "Currency"},
            ],
            "rows": [["20260615", 120.5, 0.0, "CAD"]],
        },
    })
    rows = daily_query_to_export_rows(response)
    assert rows[0]["cost"] == 120.5
    assert rows[0]["cost_usd"] == 0.0


def test_summarize_cost_response_from_api_shape():
    response = normalize_query_response({
        "properties": {
            "columns": [{"name": "PreTaxCost"}, {"name": "CostUSD"}, {"name": "Currency"}],
            "rows": [[250.0, 200.0, "CAD"]],
        },
    })
    summary = summarize_cost_response(response)
    assert summary["pretax_total"] == 250.0
    assert summary["cost_usd_total"] == 200.0
    assert summary["billing_currency"] == "CAD"


def test_resource_group_filter_uses_in_operator():
    filt = resource_group_filter(["rg-a", " rg-b ", ""])
    assert filt["dimensions"]["operator"] == "In"
    assert filt["dimensions"]["values"] == ["rg-a", "rg-b"]


def test_mtd_breakdown_single_response_feeds_service_and_resource_type():
    from app.azure_cost import normalize_query_response
    from app.cost_utils import aggregate_cost_rows_by_resource_type, aggregate_cost_rows_by_service

    response = normalize_query_response({
        "properties": {
            "columns": [
                {"name": "ServiceName"},
                {"name": "ResourceType"},
                {"name": "PreTaxCost"},
                {"name": "CostUSD"},
                {"name": "Currency"},
            ],
            "rows": [
                ["Virtual Machines", "microsoft.compute/virtualmachines", 100.0, 80.0, "CAD"],
                ["Virtual Machines", "microsoft.compute/disks", 20.0, 16.0, "CAD"],
                ["Storage", "microsoft.storage/storageaccounts", 50.0, 40.0, "CAD"],
            ],
        },
        "billing_currency": "CAD",
    })
    by_service = aggregate_cost_rows_by_service(response)
    by_type = aggregate_cost_rows_by_resource_type(response)
    assert by_service["Virtual Machines"]["pretax"] == 120.0
    assert by_service["Storage"]["pretax"] == 50.0
    assert by_type["microsoft.compute/virtualmachines"]["pretax"] == 100.0
    assert by_type["microsoft.storage/storageaccounts"]["pretax"] == 50.0


def test_aggregate_cost_rows_by_resource_type():
    from app.azure_cost import normalize_query_response
    from app.cost_utils import aggregate_cost_rows_by_resource_type

    response = normalize_query_response({
        "properties": {
            "columns": [
                {"name": "ResourceType"},
                {"name": "PreTaxCost"},
                {"name": "CostUSD"},
                {"name": "Currency"},
            ],
            "rows": [
                ["microsoft.compute/virtualmachines", 100.0, 80.0, "CAD"],
                ["microsoft.compute/virtualmachines", 50.0, 40.0, "CAD"],
                ["microsoft.storage/storageaccounts", 25.0, 20.0, "CAD"],
            ],
        },
    })
    agg = aggregate_cost_rows_by_resource_type(response)
    assert agg["microsoft.compute/virtualmachines"]["pretax"] == 150.0
    assert agg["microsoft.storage/storageaccounts"]["pretax"] == 25.0


def test_resource_type_filter_uses_in_operator():
    filt = resource_type_filter(["Microsoft.Compute/virtualMachines", " microsoft.storage/storageaccounts ", ""])
    assert filt["dimensions"]["operator"] == "In"
    assert filt["dimensions"]["values"] == [
        "microsoft.compute/virtualmachines",
        "microsoft.storage/storageaccounts",
    ]


def test_merge_query_responses_combines_rows():
    first = normalize_query_response({
        "properties": {
            "columns": [{"name": "ResourceId"}, {"name": "PreTaxCost"}],
            "rows": [["/subscriptions/x/resourcegroups/rg-a/providers/a", 10.0]],
        },
    })
    second = normalize_query_response({
        "properties": {
            "columns": [{"name": "ResourceId"}, {"name": "PreTaxCost"}],
            "rows": [["/subscriptions/x/resourcegroups/rg-b/providers/b", 5.0]],
        },
    })
    merged = merge_query_responses([first, second])
    rows = merged["properties"]["rows"]
    assert len(rows) == 2
    assert rows[0][1] == 10.0
    assert rows[1][1] == 5.0


def test_run_query_reposts_body_on_next_link(monkeypatch):
    """Pagination must resend the query body — empty POST returns 400 from Azure."""
    from app import azure_cost

    calls: list[dict | None] = []
    pages = [
        {
            "properties": {
                "columns": [{"name": "PreTaxCost"}],
                "rows": [[1.0]],
                "nextLink": "https://management.azure.com/subscriptions/x/providers/Microsoft.CostManagement/query?api-version=2024-08-01&$skiptoken=abc",
            },
        },
        {
            "properties": {
                "columns": [{"name": "PreTaxCost"}],
                "rows": [[2.0]],
            },
        },
    ]

    def fake_cost_request(method, url, headers, *, params=None, payload=None, throttle_label="cost_api", _retried=False):
        calls.append(payload)
        return pages[len(calls) - 1]

    monkeypatch.setattr(azure_cost, "_cost_request", fake_cost_request)
    monkeypatch.setattr(azure_cost, "_pause_between_cost_queries", lambda *_a, **_k: None)
    monkeypatch.setattr(azure_cost, "_headers", lambda *_a, **_k: {"Authorization": "Bearer test"})

    body = {"type": "ActualCost", "timeframe": "MonthToDate", "dataset": {"granularity": "Daily"}}
    result = azure_cost._run_query("/subscriptions/x", body, throttle_label="test")

    assert len(calls) == 2
    assert calls[0] == body
    assert calls[1] == body
    assert result["properties"]["rows"] == [[1.0], [2.0]]
