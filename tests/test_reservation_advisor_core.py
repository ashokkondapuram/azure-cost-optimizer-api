"""Tests for reservation advisor core logic."""
from types import SimpleNamespace

from app.azure_reservations import normalize_reservation, normalize_savings_plan
from app.reservation_advisor_core import (
    _advisor_commitment_type,
    _dedupe_recommendations,
    _is_reservation_advisor_row,
    build_reservation_advisor,
)


def test_normalize_reservation_maps_fields():
    item = {
        "id": "/subscriptions/x/providers/microsoft.capacity/reservations/r1",
        "name": "r1",
        "properties": {
            "displayName": "Prod RI",
            "reservedResourceType": "VirtualMachines",
            "term": "P1Y",
            "quantity": 2,
            "provisioningState": "Succeeded",
            "sku": {"name": "Standard_D4s_v3"},
            "utilization": {"aggregatedUtilization": 72.5},
        },
    }
    row = normalize_reservation(item)
    assert row["commitment_type"] == "reserved_instance"
    assert row["utilization_percent"] == 72.5
    assert row["sku_name"] == "Standard_D4s_v3"


def test_normalize_savings_plan_filters_subscription():
    item = {
        "id": "/providers/Microsoft.BillingBenefits/savingsPlans/sp1",
        "name": "sp1",
        "properties": {
            "displayName": "Compute SP",
            "term": "P1Y",
            "appliedScopes": [{"subscriptionId": "/subscriptions/abc-123"}],
            "utilizationPercentage": 88,
        },
    }
    assert normalize_savings_plan(item, "abc-123")["commitment_type"] == "savings_plan"
    assert normalize_savings_plan(item, "other-sub") == {}


def test_is_reservation_advisor_row_matches_cost_reservation_text():
    row = SimpleNamespace(
        category="Cost",
        summary="Consider purchasing a reservation for VM",
        description="",
        raw_json="{}",
    )
    assert _is_reservation_advisor_row(row) is True


def test_advisor_commitment_type_detects_savings_plan():
    row = SimpleNamespace(
        category="Cost",
        summary="Purchase savings plan",
        description="",
        raw_json='{"properties":{"recommendationTypeId":"SavingsPlan"}}',
    )
    assert _advisor_commitment_type(row) == "savings_plan"


def test_dedupe_recommendations_keeps_highest_savings():
    recs = [
        {"id": "a", "estimated_annual_savings": 100},
        {"id": "a", "estimated_annual_savings": 200},
        {"id": "b", "estimated_annual_savings": 50},
    ]
    out = _dedupe_recommendations(recs)
    assert len(out) == 2
    assert out[0]["id"] == "a"


def test_build_reservation_advisor_empty_db():
    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self
        def all(self):
            return []

    class FakeDB:
        def query(self, *args):
            return FakeQuery()

    result = build_reservation_advisor(FakeDB(), "sub-1", include_live_azure=False)
    assert result["subscription_id"] == "sub-1"
    assert result["summary"]["total_recommendations"] == 0
    assert result["warnings"]
