"""Tests for subscription MTD totals from cost sync runs."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.cost_db import cost_summary_from_db
from app.models import Base, CostByServiceSnapshot, CostSyncRun


def test_cost_summary_prefers_subscription_total_over_service_sum():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    sub = "sub-1"
    month = "2026-06"
    db.add(
        CostSyncRun(
            id="run-1",
            subscription_id=sub,
            month=month,
            mtd_start="2026-06-01",
            mtd_end="2026-06-30",
            total_billing=14600.0,
            total_usd=11000.0,
            billing_currency="CAD",
            services_json="[]",
            changes_json="[]",
            synced_at=datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
        )
    )
    db.add(
        CostByServiceSnapshot(
            id="svc-1",
            subscription_id=sub,
            service_name="Virtual Machines",
            month=month,
            cost_usd=100.0,
            cost_billing=120.0,
            billing_currency="CAD",
        )
    )
    db.commit()

    summary = cost_summary_from_db(db, sub, timeframe="MonthToDate", month=month)
    assert summary is not None
    assert summary["pretax_total"] == 14600.0
    assert summary["total_source"] == "azure_subscription_query"
    assert summary["synced_at"] is not None
    db.close()


def test_cost_summary_this_year_sums_completed_months_plus_current_mtd(monkeypatch):
    """YTD must include prior months from monthly snapshots, not only current-month daily rows."""
    from datetime import date

    from app.models import CostDailyByServiceSnapshot

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    sub = "sub-1"
    for month, amount in [("2026-01", 1000.0), ("2026-02", 2000.0), ("2026-03", 1500.0)]:
        db.add(
            CostByServiceSnapshot(
                id=f"svc-{month}",
                subscription_id=sub,
                service_name="Virtual Machines",
                month=month,
                cost_usd=amount,
                cost_billing=amount,
                billing_currency="CAD",
            )
        )
    db.add(
        CostDailyByServiceSnapshot(
            id="daily-1",
            subscription_id=sub,
            cost_date="2026-07-01",
            service_name="__subscription__",
            cost_billing=100.0,
            cost_usd=80.0,
            billing_currency="CAD",
        )
    )
    db.add(
        CostDailyByServiceSnapshot(
            id="daily-2",
            subscription_id=sub,
            cost_date="2026-07-02",
            service_name="__subscription__",
            cost_billing=150.0,
            cost_usd=120.0,
            billing_currency="CAD",
        )
    )
    db.commit()

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 2)

    monkeypatch.setattr("app.cost_timeframes.date", FixedDate)

    summary = cost_summary_from_db(db, sub, timeframe="ThisYear")
    assert summary is not None
    assert summary["pretax_total"] == 4750.0
    assert summary["total_source"] == "multi_month_aggregate"
    assert summary["period_start"] == "2026-01-01"
    assert summary["period_end"] == "2026-07-02"
    db.close()
