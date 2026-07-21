"""Verify FOCUS blob column mapping — no semantic mistakes."""
from __future__ import annotations

from datetime import date
from app.cost_export import (
    _normalize_row,
    _parse_csv_stream,
    _parse_csv_text,
    by_resource_response,
    by_service_response,
    filter_rows_by_timeframe,
    ParsedCostExport,
    resolve_mtd_rows,
    resolve_parsed_mtd,
)
from app.focus_mapping import (
    COL_BILLED_COST,
    COL_BILLED_USD,
    COL_BILLING_CURRENCY,
    COL_SERVICE_NAME,
    COL_USAGE_DATE,
    PICK_BILLED_COST,
    PICK_BILLED_USD,
    normalize_arm_id,
    normalize_usage_date,
)


FOCUS_ROW = {
    "BilledCost": "12.50",
    "x_BilledCostInUsd": "9.25",
    "BillingCurrency": "CAD",
    "SubAccountId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "ResourceId": "/subscriptions/a1b2c3d4-e5f6-7890-abcd-ef1234567890/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/vm1",
    "ResourceType": "microsoft.compute/virtualmachines",
    "x_ResourceType": "microsoft.compute/virtualmachines",
    "x_ResourceGroupName": "rg-prod",
    "ServiceName": "Virtual Machines",
    "ChargePeriodStart": "2026-06-15T00:00:00Z",
    "EffectiveCost": "99.99",
    "x_EffectiveCostInUsd": "77.77",
    "x_PricingCurrency": "USD",
    "ServiceCategory": "Compute",
}


def test_normalize_legacy_us_date():
    assert normalize_usage_date("06/15/2026") == "2026-06-15"
    assert normalize_usage_date("6/5/2026") == "2026-06-05"
    assert normalize_usage_date("2026-06-15T00:00:00Z") == "2026-06-15"


LEGACY_ACTUAL_ROW = {
    "SubscriptionId": "93ca908b-5732-440d-b712-f6d7951951c0",
    "ResourceGroup": "MC_PNCDEVV2RG1EU2_PNCDEVV2RG1EU2_EASTUS2",
    "Date": "06/15/2026",
    "MeterCategory": "Storage",
    "ConsumedService": "Microsoft.Compute",
    "CostInBillingCurrency": "0.61604928",
    "BillingCurrencyCode": "CAD",
    "ResourceId": "/subscriptions/93ca908b-5732-440d-b712-f6d7951951c0/resourceGroups/MC_PNCDEVV2RG1EU2_PNCDEVV2RG1EU2_EASTUS2/providers/Microsoft.Compute/disks/aks-flink-18610949-vaks-flink-18610949-vmOS__1_48155e35d6bc48dea4af3299a4c84d2c",
}


def test_normalize_legacy_actual_export_row():
    row = _normalize_row(LEGACY_ACTUAL_ROW)
    assert row["date"] == "2026-06-15"
    assert row["cost"] == 0.61604928
    assert row["currency"] == "CAD"
    assert row["service_name"] == "Storage"
    assert row["resource_group"] == "MC_PNCDEVV2RG1EU2_PNCDEVV2RG1EU2_EASTUS2"
    assert "disks/aks-flink" in row["resource_id"]


def test_legacy_date_month_filter():
    row = _normalize_row(LEGACY_ACTUAL_ROW)
    mtd, month, mtd_start, mtd_end = resolve_mtd_rows([row])
    assert month == "2026-06"
    assert len(mtd) == 1
    assert mtd_end >= mtd_start


def test_focus_primary_columns_defined():
    assert COL_BILLED_COST == ["BilledCost"]
    assert COL_BILLED_USD == ["x_BilledCostInUsd"]
    assert COL_BILLING_CURRENCY == ["BillingCurrency"]
    assert COL_SERVICE_NAME[0] == "ServiceName"
    assert COL_USAGE_DATE[0] == "ChargePeriodStart"


def test_effective_cost_not_in_pick_lists():
    assert "EffectiveCost" not in PICK_BILLED_COST
    assert "x_EffectiveCostInUsd" not in PICK_BILLED_USD
    assert "x_PricingCurrency" not in COL_BILLING_CURRENCY


def test_normalize_focus_row_billed_and_usd():
    row = _normalize_row(FOCUS_ROW)
    assert row["cost"] == 12.50
    assert row["cost_usd"] == 9.25
    assert row["currency"] == "CAD"
    assert row["service_name"] == "Virtual Machines"
    assert row["resource_group"] == "rg-prod"
    assert row["date"] == "2026-06-15"
    assert row["resource_id"].endswith("/virtualmachines/vm1")


def test_service_category_not_used_as_service_name():
    row = dict(FOCUS_ROW)
    row.pop("ServiceName", None)
    row.pop("x_SkuMeterCategory", None)
    row["ServiceCategory"] = "Compute"
    row["MeterCategory"] = "Virtual Machines"
    normalized = _normalize_row(row)
    assert normalized["service_name"] == "Virtual Machines"


def test_missing_usd_does_not_copy_billing_amount():
    row = dict(FOCUS_ROW)
    row["x_BilledCostInUsd"] = ""
    normalized = _normalize_row(row)
    assert normalized["cost"] == 12.50
    assert normalized["cost_usd"] == 0.0


def test_resource_group_from_resource_id_when_column_empty():
    row = dict(FOCUS_ROW)
    row["x_ResourceGroupName"] = ""
    normalized = _normalize_row(row)
    assert normalized["resource_group"] == "rg-prod"


def test_subscription_filter_in_csv_parse():
    csv_text = (
        "BilledCost,x_BilledCostInUsd,BillingCurrency,SubAccountId,ResourceId,"
        "x_ResourceGroupName,ServiceName,ResourceType,ChargePeriodStart\n"
        "1.00,0.75,CAD,a1b2c3d4-e5f6-7890-abcd-ef1234567890,"
        "/subscriptions/a1b2c3d4-e5f6-7890-abcd-ef1234567890/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/sa1,"
        "rg,Storage,microsoft.storage/storageaccounts,2026-06-01T00:00:00Z\n"
        "2.00,1.50,CAD,00000000-0000-0000-0000-000000000000,"
        "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/other/providers/Microsoft.Compute/virtualMachines/vm2,"
        "other,Virtual Machines,microsoft.compute/virtualmachines,2026-06-01T00:00:00Z\n"
    )
    rows, stats = _parse_csv_text(csv_text, "a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    assert len(rows) == 1
    assert stats["skipped_subscription"] == 1
    assert rows[0]["service_name"] == "Storage"
    assert rows[0]["cost"] == 1.0


def test_by_service_aggregates_billed_cost():
    rows = [
        {"service_name": "Storage", "cost": 10.0, "cost_usd": 7.5, "currency": "CAD", "date": "2026-06-01",
         "resource_id": "/a", "resource_group": "rg", "resource_type": "t"},
        {"service_name": "Storage", "cost": 5.0, "cost_usd": 3.75, "currency": "CAD", "date": "2026-06-02",
         "resource_id": "/b", "resource_group": "rg", "resource_type": "t"},
    ]
    resp = by_service_response(rows)
    data_rows = resp["properties"]["rows"]
    assert len(data_rows) == 1
    assert data_rows[0][0] == "Storage"
    assert data_rows[0][1] == 15.0  # PreTaxCost
    assert data_rows[0][2] == 11.25  # CostUSD


def test_by_resource_keeps_service_name_on_aggregate():
    rid = "/subscriptions/x/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1"
    rows = [
        {"resource_id": rid, "service_name": "Virtual Machines", "cost": 3.0, "cost_usd": 2.0,
         "currency": "CAD", "date": "2026-06-01", "resource_group": "rg", "resource_type": "microsoft.compute/virtualmachines"},
        {"resource_id": rid, "service_name": "Virtual Machines", "cost": 2.0, "cost_usd": 1.5,
         "currency": "CAD", "date": "2026-06-02", "resource_group": "rg", "resource_type": "microsoft.compute/virtualmachines"},
    ]
    resp = by_resource_response(rows)
    row = resp["properties"]["rows"][0]
    assert row[0] == rid
    assert row[3] == "Virtual Machines"
    assert row[4] == 5.0
    assert row[5] == 3.5


def test_normalize_arm_id_strips_trailing_slash():
    base = "/subscriptions/x/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1"
    assert normalize_arm_id(f"{base}/") == base


def test_by_resource_merges_trailing_slash_resource_ids():
    base = "/subscriptions/x/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1"
    rows = [
        {"resource_id": base, "service_name": "Virtual Machines", "cost": 3.0, "cost_usd": 2.0,
         "currency": "CAD", "date": "2026-06-01", "resource_group": "rg", "resource_type": "t"},
        {"resource_id": f"{base}/", "service_name": "Virtual Machines", "cost": 2.0, "cost_usd": 1.5,
         "currency": "CAD", "date": "2026-06-02", "resource_group": "rg", "resource_type": "t"},
    ]
    resp = by_resource_response(rows)
    assert len(resp["properties"]["rows"]) == 1
    assert resp["properties"]["rows"][0][4] == 5.0


def test_timeframe_filter_month_to_date():
    from datetime import date

    today = date.today()
    in_month = today.replace(day=1).isoformat()
    if today.day == 1:
        import calendar
        prev = today.replace(day=1) - __import__("datetime").timedelta(days=1)
        out_month = prev.isoformat()
    else:
        out_month = today.replace(day=1) - __import__("datetime").timedelta(days=1)
        out_month = out_month.isoformat()

    rows = [
        {"date": in_month, "cost": 1, "cost_usd": 1, "currency": "USD",
         "service_name": "S", "resource_id": "", "resource_group": "", "resource_type": ""},
        {"date": out_month, "cost": 9, "cost_usd": 9, "currency": "USD",
         "service_name": "S", "resource_id": "", "resource_group": "", "resource_type": ""},
    ]
    filtered = filter_rows_by_timeframe(rows, "MonthToDate")
    assert len(filtered) == 1
    assert filtered[0]["date"] == in_month


def test_resolve_mtd_rows_falls_back_to_latest_month():
    rows = [
        {"date": "2026-04-01", "cost": 1, "cost_usd": 1, "currency": "USD",
         "service_name": "Storage", "resource_id": "/a", "resource_group": "rg", "resource_type": "t"},
        {"date": "2026-05-15", "cost": 2, "cost_usd": 2, "currency": "USD",
         "service_name": "Compute", "resource_id": "/b", "resource_group": "rg", "resource_type": "t"},
        {"date": "2026-05-20", "cost": 3, "cost_usd": 3, "currency": "USD",
         "service_name": "Compute", "resource_id": "/c", "resource_group": "rg", "resource_type": "t"},
    ]
    mtd, month, _mtd_start, _mtd_end = resolve_mtd_rows(rows)
    if date.today().strftime("%Y-%m") == "2026-05":
        assert month == "2026-05"
        assert len(mtd) == 2
    elif date.today().strftime("%Y-%m") == "2026-06":
        assert month == "2026-05"
        assert len(mtd) == 2
    else:
        assert len(mtd) >= 1


def test_streaming_parse_builds_aggregates():
    import io

    csv_text = (
        "BilledCost,x_BilledCostInUsd,BillingCurrency,SubAccountId,ResourceId,"
        "x_ResourceGroupName,ServiceName,ResourceType,ChargePeriodStart\n"
        "10.00,7.50,CAD,a1b2c3d4-e5f6-7890-abcd-ef1234567890,"
        "/subscriptions/a1b2c3d4-e5f6-7890-abcd-ef1234567890/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/sa1,"
        "rg,Storage,microsoft.storage/storageaccounts,2026-06-01T00:00:00Z\n"
        "5.00,3.75,CAD,a1b2c3d4-e5f6-7890-abcd-ef1234567890,"
        "/subscriptions/a1b2c3d4-e5f6-7890-abcd-ef1234567890/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1,"
        "rg,Virtual Machines,microsoft.compute/virtualmachines,2026-06-02T00:00:00Z\n"
    )
    parsed = ParsedCostExport()
    _parse_csv_stream(
        io.StringIO(csv_text),
        "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        parsed=parsed,
    )
    assert parsed.parsed_rows == 2
    assert parsed.services_by_month["2026-06"]["Storage"]["pretax"] == 10.0
    assert parsed.services_by_month["2026-06"]["Virtual Machines"]["pretax"] == 5.0
    assert len(parsed.resources_by_month["2026-06"]) == 2
    assert len(parsed.daily_by_rg) == 2


def test_resolve_parsed_mtd_matches_row_resolver():
    rows = [
        {"date": "2026-05-15", "cost": 2, "cost_usd": 2, "currency": "USD",
         "service_name": "Compute", "resource_id": "/b", "resource_group": "rg", "resource_type": "t"},
        {"date": "2026-05-20", "cost": 3, "cost_usd": 3, "currency": "USD",
         "service_name": "Compute", "resource_id": "/c", "resource_group": "rg", "resource_type": "t"},
    ]
    parsed = ParsedCostExport()
    for row in rows:
        from app.cost_export import _ingest_normalized_row
        _ingest_normalized_row(parsed, row)
    _mtd_rows, month, _start, _end = resolve_mtd_rows(rows)
    _parsed_month, _ps, _pe, services, resources, mtd_count = resolve_parsed_mtd(parsed)
    if date.today().strftime("%Y-%m") != "2026-05":
        assert month == _parsed_month
    assert mtd_count == len(_mtd_rows)
    assert round(services.get("Compute", {}).get("pretax", 0), 2) == round(
        sum(r["cost"] for r in _mtd_rows if r["service_name"] == "Compute"), 2
    )
    assert len(resources) == len({r["resource_id"] for r in _mtd_rows})
