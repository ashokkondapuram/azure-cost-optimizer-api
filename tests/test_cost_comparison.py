"""Unit tests for cost period comparison helpers."""

from app.cost_comparison import build_cost_comparison, build_service_deltas


def test_build_service_deltas_sorted_by_abs_change():
    rows = build_service_deltas(
        {"Virtual Machines": 100.0, "Storage": 20.0},
        {"Virtual Machines": 80.0, "Storage": 25.0},
    )
    assert rows[0]["service"] == "Virtual Machines"
    assert rows[0]["delta"] == 20.0
    assert rows[0]["pct_change"] == 25.0


def test_build_cost_comparison_totals_and_delta():
    payload = build_cost_comparison(
        current_summary={"pretax_total": 150.0, "billing_currency": "CAD"},
        compare_summary={"pretax_total": 100.0, "billing_currency": "CAD"},
        current_services={
            "properties": {
                "columns": [{"name": "ServiceName"}, {"name": "PreTaxCost"}],
                "rows": [["Compute", 150.0]],
            }
        },
        compare_services={
            "properties": {
                "columns": [{"name": "ServiceName"}, {"name": "PreTaxCost"}],
                "rows": [["Compute", 100.0]],
            }
        },
    )
    assert payload["current_total"] == 150.0
    assert payload["compare_total"] == 100.0
    assert payload["delta"] == 50.0
    assert payload["pct_change"] == 50.0
    assert payload["currency"] == "CAD"
    assert payload["services"][0]["service"] == "Compute"
