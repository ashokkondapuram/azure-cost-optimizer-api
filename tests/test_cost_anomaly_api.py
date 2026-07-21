"""Tests for cost anomaly daily API."""
from datetime import date, timedelta

from app.routers.cost_anomaly import _daily_totals, _detect_anomalies, get_cost_anomalies


def test_daily_totals_includes_subscription_rollup(monkeypatch):
    """Cost sync stores daily totals under __subscription__ — anomaly API must read them."""
    sub = "sub-1"
    start = date.today() - timedelta(days=5)
    end = date.today()

    class FakeRow:
        def __init__(self, cost_date, total, currency="CAD"):
            self.cost_date = cost_date
            self.total = total
            self.currency = currency

    class FakeQuery:
        def __init__(self):
            self._rollup = True

        def filter(self, *args, **kwargs):
            return self

        def limit(self, *args):
            return self

        def first(self):
            return object() if self._rollup else None

        def group_by(self, *args):
            return self

        def order_by(self, *args):
            return self

        def all(self):
            base = start
            return [
                FakeRow((base + timedelta(days=i)).isoformat(), 100.0 + i)
                for i in range(6)
            ]

    class FakeDB:
        def query(self, *args):
            return FakeQuery()

    rows = _daily_totals(FakeDB(), sub, start, end)
    assert len(rows) == 6
    assert rows[0]["total"] == 100.0


def test_detect_anomalies_flags_spike():
    daily = []
    base = date(2025, 1, 1)
    for i in range(40):
        daily.append({
            "date": (base + timedelta(days=i)).isoformat(),
            "total": 100.0 + (i % 5),
            "currency": "CAD",
        })
    daily[-1]["total"] = 500.0
    anomalies = _detect_anomalies(daily, 30, 2.0, 7)
    assert anomalies
    assert anomalies[0]["direction"] == "spike"


def test_daily_endpoint_includes_series(monkeypatch):
    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def limit(self, *args):
            return self

        def first(self):
            return object()

        def group_by(self, *args):
            return self

        def order_by(self, *args):
            return self

        def all(self):
            base = date.today() - timedelta(days=5)
            return [
                type("Row", (), {
                    "cost_date": (base + timedelta(days=i)).isoformat(),
                    "total": 100.0 + i,
                    "currency": "CAD",
                })()
                for i in range(6)
            ]

    class FakeDB:
        def query(self, *args):
            return FakeQuery()

    result = get_cost_anomalies("sub-1", window_days=30, threshold_sigma=2.0, lookback_days=7, db=FakeDB())
    assert "series" in result
    assert len(result["series"]) == 6
    assert result["series"][0]["total"] is not None
    assert result.get("insufficient_history") is True
    assert result["anomaly_count"] == 0
