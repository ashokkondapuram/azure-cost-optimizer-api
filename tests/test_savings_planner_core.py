"""Tests for savings planner estimate builder."""
from datetime import date, timedelta
from unittest.mock import patch

from app.savings_planner_core import (
    _azure_savings_by_plan,
    _categorize_service,
    _plan_rows,
    build_savings_estimate,
)


def test_categorize_service_vm():
    cat_id, label = _categorize_service("Virtual Machines")
    assert cat_id == "vms"
    assert "Virtual" in label


def test_plan_rows_include_savings_plans():
    rows = _plan_rows(1000.0)
    ids = {r["id"] for r in rows}
    assert "payg" in ids
    assert "savings_plan_1yr" in ids
    assert "savings_plan_3yr" in ids
    sp1 = next(r for r in rows if r["id"] == "savings_plan_1yr")
    assert sp1["monthly_saving"] > 0


def test_build_estimate_empty_db():
    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self
        def group_by(self, *args):
            return self
        def all(self):
            return []

    class FakeFindingsQuery:
        def filter(self, *args, **kwargs):
            return self
        def order_by(self, *args):
            return self
        def limit(self, *args):
            return self
        def all(self):
            return []

    class FakeAdvisorQuery:
        def filter(self, *args, **kwargs):
            return self
        def all(self):
            return []

    class FakeDB:
        def query(self, *args):
            from app.models import AdvisorRecommendation, OptimizationFinding
            if args and args[0] is OptimizationFinding:
                return FakeFindingsQuery()
            if args and args[0] is AdvisorRecommendation:
                return FakeAdvisorQuery()
            return FakeQuery()

    result = build_savings_estimate(FakeDB(), "sub-1", include_live_azure=False)
    assert result["monthly_baseline"] == 0
    assert result["message"]
    assert len(result["plans"]) >= 3
    assert "sources" in result
    assert result["sources"]["cost_baseline"] == "empty"


def test_build_estimate_with_service_rows():
    class Row:
        def __init__(self, service_name, total, currency="CAD"):
            self.service_name = service_name
            self.total = total
            self.currency = currency

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self
        def group_by(self, *args):
            return self
        def all(self):
            return [Row("Virtual Machines", 3000.0), Row("Storage", 200.0)]

    class FakeFindingsQuery:
        def filter(self, *args, **kwargs):
            return self
        def order_by(self, *args):
            return self
        def limit(self, *args):
            return self
        def all(self):
            return []

    class FakeAdvisorQuery:
        def filter(self, *args, **kwargs):
            return self
        def all(self):
            return []

    class FakeDB:
        def query(self, *args):
            from app.models import AdvisorRecommendation, OptimizationFinding
            if args and args[0] is OptimizationFinding:
                return FakeFindingsQuery()
            if args and args[0] is AdvisorRecommendation:
                return FakeAdvisorQuery()
            return FakeQuery()

    result = build_savings_estimate(FakeDB(), "sub-1", include_live_azure=False)
    assert result["monthly_baseline"] == 3200.0
    assert result["billing_currency"] == "CAD"
    assert any(c["id"] == "vms" for c in result["all_categories"])
    assert result["recommended_plan_id"] != "payg"
    assert result["sources"]["cost_baseline"] == "database"


def test_azure_savings_by_plan_merges_advisor_and_capacity():
    advisor = [{
        "commitment_type": "savings_plan",
        "title": "Purchase savings plan",
        "estimated_monthly_savings": 500.0,
    }]
    capacity = [{
        "plan_id": "reserved_instance_1yr",
        "monthly_saving": 300.0,
    }]
    savings = _azure_savings_by_plan(advisor, capacity)
    assert savings["savings_plan_1yr"] == 500.0
    assert savings["reserved_instance_1yr"] == 300.0


def test_plan_rows_use_azure_backed_saving():
    rows = _plan_rows(1000.0, azure_savings={"savings_plan_1yr": 400.0})
    sp1 = next(r for r in rows if r["id"] == "savings_plan_1yr")
    assert sp1["monthly_saving"] == 400.0
    assert sp1["data_source"] == "azure"


@patch("app.savings_planner_core.fetch_live_commitments")
@patch("app.savings_planner_core.query_cost_by_service_live")
def test_build_estimate_prefers_live_azure_cost(mock_live_cost, mock_live_commitments):
    end = date.today()
    start = end - timedelta(days=30)

    mock_live_cost.return_value = {
        "billing_currency": "USD",
        "properties": {
            "rows": [
                ["Virtual Machines", 2500.0, 2500.0, "USD"],
                ["Storage", 100.0, 100.0, "USD"],
            ],
        },
    }
    mock_live_commitments.return_value = {
        "reservations": [{"id": "/ri/1", "display_name": "VM RI", "commitment_type": "reserved_instance", "term": "P1Y"}],
        "savings_plans": [],
        "reservation_recommendations": [{
            "id": "/rec/1",
            "plan_id": "reserved_instance_1yr",
            "monthly_saving": 200.0,
            "sku_name": "Standard_D2s_v3",
            "term": "P1Y",
            "years": 1,
        }],
    }

    class FakeFindingsQuery:
        def filter(self, *args, **kwargs):
            return self
        def order_by(self, *args):
            return self
        def limit(self, *args):
            return self
        def all(self):
            return []

    class FakeAdvisorQuery:
        def filter(self, *args, **kwargs):
            return self
        def all(self):
            return []

    class FakeDB:
        def query(self, *args):
            from app.models import AdvisorRecommendation, OptimizationFinding
            if args and args[0] is OptimizationFinding:
                return FakeFindingsQuery()
            if args and args[0] is AdvisorRecommendation:
                return FakeAdvisorQuery()
            raise AssertionError(f"unexpected query: {args}")

    result = build_savings_estimate(
        FakeDB(),
        "sub-1",
        headers={"Authorization": "Bearer test"},
        include_live_azure=True,
    )
    assert result["sources"]["cost_baseline"] == "azure_live"
    assert result["sources"]["azure_inventory"] is True
    assert result["sources"]["azure_reservation_recommendations"] is True
    assert result["monthly_baseline"] == 2600.0
    assert result["billing_currency"] == "USD"
    assert len(result["active_commitments"]) == 1
    assert len(result["azure_reservation_recommendations"]) == 1
    mock_live_cost.assert_called_once()
    assert mock_live_cost.call_args[0][1] == "sub-1"
    assert mock_live_cost.call_args[0][2] == "Custom"
    assert mock_live_cost.call_args[1]["from_date"] == start.isoformat()
    assert mock_live_cost.call_args[1]["to_date"] == end.isoformat()
