"""Tests for cost helper utilities."""

import pytest

from app.cost_utils import (
    aggregate_cost_rows_by_service,
    billing_cost_map_from_details,
    by_service_properties_from_response,
    by_resource_properties_from_response,
    normalize_monthly_cost_usd,
    project_mtd_to_monthly_run_rate,
    parse_cost_by_resource_details,
    resource_cost_billing_from_map,
    resource_cost_usd_from_map,
    service_name_from_cost_row,
    usd_cost_map_from_details,
    cost_column_indices,
)


def test_service_name_from_cost_row_uses_meter_category_when_service_blank():
    cols = [
        {"name": "ServiceName"},
        {"name": "MeterCategory"},
        {"name": "PreTaxCost"},
    ]
    idx = cost_column_indices(cols)
    row = ["", "Virtual Machines", 10.0]
    assert service_name_from_cost_row(row, idx, names=["ServiceName", "MeterCategory", "PreTaxCost"]) == "Virtual Machines"


def test_service_name_from_cost_row_maps_consumed_service():
    cols = [{"name": "ConsumedService"}, {"name": "PreTaxCost"}]
    idx = cost_column_indices(cols)
    row = ["Microsoft.Storage", 25.0]
    assert service_name_from_cost_row(row, idx, names=["ConsumedService", "PreTaxCost"]) == "Storage"


def test_service_name_from_cost_row_maps_resource_type():
    cols = [{"name": "ResourceType"}, {"name": "PreTaxCost"}]
    idx = cost_column_indices(cols)
    row = ["microsoft.compute/virtualmachines", 40.0]
    assert service_name_from_cost_row(row, idx, names=["ResourceType", "PreTaxCost"]) == "Virtual Machines"


def test_aggregate_cost_rows_by_service_splits_by_resolved_service():
    response = {
        "billing_currency": "CAD",
        "properties": {
            "columns": [
                {"name": "ServiceName"},
                {"name": "MeterCategory"},
                {"name": "PreTaxCost"},
                {"name": "CostUSD"},
                {"name": "Currency"},
            ],
            "rows": [
                ["", "Virtual Machines", 100.0, 80.0, "CAD"],
                ["", "Storage", 25.0, 20.0, "CAD"],
            ],
        },
    }
    agg = aggregate_cost_rows_by_service(response)
    assert agg["Virtual Machines"]["pretax"] == pytest.approx(100.0)
    assert agg["Storage"]["pretax"] == pytest.approx(25.0)
    assert "Other" not in agg


def test_by_service_properties_from_response_normalizes_meter_category_rows():
    response = {
        "billing_currency": "CAD",
        "properties": {
            "columns": [
                {"name": "ServiceName"},
                {"name": "MeterCategory"},
                {"name": "PreTaxCost"},
                {"name": "CostUSD"},
                {"name": "Currency"},
            ],
            "rows": [
                ["", "Virtual Machines", 3547.06, 5036.65, "CAD"],
                ["", "Storage", 999.53, 1419.28, "CAD"],
            ],
        },
    }
    props = by_service_properties_from_response(response)
    assert props is not None
    assert [c["name"] for c in props["columns"]] == [
        "ServiceName", "PreTaxCost", "CostUSD", "Currency",
    ]
    assert props["rows"][0][0] == "Virtual Machines"
    assert props["rows"][0][1] == pytest.approx(3547.06)
    assert props["rows"][0][2] == pytest.approx(5036.65)
    assert props["rows"][1][0] == "Storage"


def test_by_resource_properties_from_response_normalizes_rows():
    rid = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1"
    response = {
        "billing_currency": "CAD",
        "properties": {
            "columns": [
                {"name": "ResourceId"},
                {"name": "ResourceType"},
                {"name": "ResourceGroupName"},
                {"name": "ServiceName"},
                {"name": "PreTaxCost"},
                {"name": "CostUSD"},
                {"name": "Currency"},
            ],
            "rows": [
                [rid, "microsoft.compute/virtualmachines", "rg", "Virtual Machines", 120.0, 95.0, "CAD"],
            ],
        },
    }
    props = by_resource_properties_from_response(response)
    assert props is not None
    assert props["rows"][0][0] == rid.lower()
    assert props["rows"][0][3] == "Virtual Machines"
    assert props["rows"][0][4] == pytest.approx(120.0)


def test_parse_cost_by_resource_details_aggregates_multiple_services():
    rid = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1"
    response = {
        "properties": {
            "columns": [
                {"name": "ResourceId"},
                {"name": "ServiceName"},
                {"name": "ResourceGroup"},
                {"name": "ResourceType"},
                {"name": "PreTaxCost"},
                {"name": "CostUSD"},
                {"name": "Currency"},
            ],
            "rows": [
                [rid, "Virtual Machines", "rg-apps", "microsoft.compute/virtualmachines", 100.0, 80.0, "CAD"],
                [rid, "Bandwidth", "rg-apps", "microsoft.compute/virtualmachines", 25.0, 20.0, "CAD"],
            ],
        },
    }
    details = parse_cost_by_resource_details(response)
    assert len(details) == 1
    bucket = details[rid]
    assert bucket["pretax"] == pytest.approx(125.0)
    assert bucket["usd"] == pytest.approx(100.0)
    assert bucket["currency"] == "CAD"
    assert bucket["resource_group"] == "rg-apps"
    assert bucket["resource_type"] == "microsoft.compute/virtualmachines"
    assert bucket["service_name"] == "Virtual Machines"


def test_billing_cost_map_from_details_uses_pretax_as_reported():
    rid = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1"
    details = {
        rid: {"pretax": 125.0, "usd": 100.0, "currency": "CAD", "service_name": "Virtual Machines"},
    }
    assert billing_cost_map_from_details(details) == {rid: pytest.approx(125.0)}


def test_resource_cost_billing_from_map_returns_pretax():
    rid = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1"
    cost_map = {
        rid: {"pretax": 125.0, "usd": 100.0, "currency": "CAD", "service_name": "Virtual Machines"},
    }
    assert resource_cost_billing_from_map(cost_map, rid) == pytest.approx(125.0)


def test_usd_cost_map_from_details_prefers_usd_over_billing_currency():
    rid = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1"
    details = {
        rid: {"pretax": 125.0, "usd": 100.0, "currency": "CAD", "service_name": "Virtual Machines"},
    }
    assert usd_cost_map_from_details(details) == {rid: pytest.approx(100.0)}


def test_resource_cost_usd_from_map_prefers_usd():
    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
    cost_map = {
        rid.lower(): {"pretax": 50.0, "usd": 45.5, "currency": "USD", "service_name": "Virtual Machines"},
    }
    assert resource_cost_usd_from_map(cost_map, rid) == pytest.approx(45.5)


def test_resource_cost_usd_from_map_skips_foreign_pretax_when_usd_zero():
    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
    cost_map = {
        rid.lower(): {"pretax": 50.0, "usd": 0.0, "currency": "CAD", "service_name": "Virtual Machines"},
    }
    assert resource_cost_usd_from_map(cost_map, rid) is None


def test_resource_cost_usd_from_map_uses_pretax_for_usd_billing():
    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
    cost_map = {
        rid.lower(): {"pretax": 50.0, "usd": 0.0, "currency": "USD", "service_name": "Virtual Machines"},
    }
    assert resource_cost_usd_from_map(cost_map, rid) == pytest.approx(50.0)


def test_resource_cost_usd_from_map_rejects_invalid_values():
    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
    cost_map = {rid.lower(): {"pretax": "not-a-number", "usd": "bad", "currency": "USD"}}
    assert resource_cost_usd_from_map(cost_map, rid) is None


def test_normalize_monthly_cost_usd_from_dict():
    assert normalize_monthly_cost_usd({"usd": 95.0, "pretax": 100.0, "currency": "USD"}) == pytest.approx(95.0)


def test_normalize_monthly_cost_usd_zero_returns_none():
    assert normalize_monthly_cost_usd(0.0) is None
    assert normalize_monthly_cost_usd({"usd": 0.0, "pretax": 0.0, "currency": "USD"}) is None


def test_project_mtd_to_monthly_run_rate():
    from datetime import date

    assert project_mtd_to_monthly_run_rate(70.0, as_of=date(2026, 7, 7)) == pytest.approx(310.0)


def test_monthly_cost_from_snapshot_prefers_billing():
    from types import SimpleNamespace
    from app.cost_utils import monthly_cost_from_snapshot

    snap = SimpleNamespace(monthly_cost_billing=88.5, monthly_cost_usd=0.0)
    assert monthly_cost_from_snapshot(snap) == pytest.approx(88.5)


def test_apply_costs_lifetime_zero_preserves_mtd():
    from app.resource_store import apply_costs_to_resources

    rid = "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/disks/d1"
    rows = apply_costs_to_resources(
        [{"id": rid, "monthlyCostBilling": 0.0, "monthlyCostUsd": 0.0}],
        {rid.lower(): {"pretax": 42.0, "usd": 0.0, "currency": "CAD"}},
        lifetime_map={rid.lower(): {"pretax": 0.0, "usd": 0.0, "currency": "CAD"}},
    )
    row = rows[0]
    assert row["monthlyCostBilling"] == pytest.approx(42.0)
    assert "totalCostBilling" not in row


def test_apply_costs_preserves_snapshot_when_map_misses():
    from app.resource_store import apply_costs_to_resources

    row = {
        "id": "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/disks/d1",
        "monthlyCostBilling": 88.5,
        "monthlyCostUsd": 0.0,
    }
    apply_costs_to_resources([row], {})
    assert row["monthlyCostBilling"] == pytest.approx(88.5)


def test_apply_costs_uses_map_billing_when_usd_zero():
    from app.resource_store import apply_costs_to_resources

    rid = "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/disks/d1"
    row = {"id": rid, "monthlyCostBilling": 0.0, "monthlyCostUsd": 0.0}
    apply_costs_to_resources([row], {
        rid.lower(): {"pretax": 120.0, "usd": 0.0, "currency": "CAD"},
    })
    assert row["monthlyCostBilling"] == pytest.approx(120.0)
    assert row["billingCurrency"] == "CAD"


def test_resolve_cost_month_uses_resource_rows_without_service_rows():
    import uuid

    from app.cost_db import _resolve_cost_month, resource_cost_map_from_db
    from app.database import SessionLocal, init_db
    from app.models import CostByResourceSnapshot

    init_db()
    db = SessionLocal()
    try:
        sub = f"cost-sub-{uuid.uuid4().hex[:8]}"
        month = "2026-06"
        db.add(
            CostByResourceSnapshot(
                id=str(uuid.uuid4()),
                subscription_id=sub,
                resource_id="/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/d1",
                service_name="Virtual Machines",
                month=month,
                cost_usd=0.0,
                cost_billing=42.0,
                billing_currency="CAD",
            )
        )
        db.commit()
        assert _resolve_cost_month(db, sub, "MonthToDate", month) == month
        cost_map = resource_cost_map_from_db(db, sub, month=month)
        assert cost_map["/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/d1"]["pretax"] == pytest.approx(42.0)
    finally:
        db.close()
