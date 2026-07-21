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


def test_cost_summary_mtd_uses_daily_rows_when_no_sync_run(monkeypatch):
    """MTD must aggregate daily rows for the current month when no sync run exists."""
    from datetime import date

    from app.models import CostDailyByServiceSnapshot

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    sub = "sub-1"
    db.add(
        CostDailyByServiceSnapshot(
            id="daily-1",
            subscription_id=sub,
            cost_date="2026-07-01",
            service_name="__subscription__",
            cost_billing=200.0,
            cost_usd=160.0,
            billing_currency="CAD",
        )
    )
    db.add(
        CostDailyByServiceSnapshot(
            id="daily-2",
            subscription_id=sub,
            cost_date="2026-07-02",
            service_name="__subscription__",
            cost_billing=300.0,
            cost_usd=240.0,
            billing_currency="CAD",
        )
    )
    db.commit()

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 2)

    monkeypatch.setattr("app.cost_timeframes.date", FixedDate)

    summary = cost_summary_from_db(db, sub, timeframe="MonthToDate")
    assert summary is not None
    assert summary["pretax_total"] == 500.0
    assert summary["total_source"] == "daily_rows_sum"
    assert summary["period_start"] == "2026-07-01"
    assert summary["period_end"] == "2026-07-02"
    db.close()


def test_cost_summary_mtd_does_not_fallback_to_previous_month(monkeypatch):
    """MTD must not substitute last month's spend when the current month has no data."""
    from datetime import date

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    sub = "sub-1"
    db.add(
        CostByServiceSnapshot(
            id="svc-june",
            subscription_id=sub,
            service_name="Virtual Machines",
            month="2026-06",
            cost_usd=9000.0,
            cost_billing=9000.0,
            billing_currency="CAD",
        )
    )
    db.commit()

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 6)

    monkeypatch.setattr("app.cost_timeframes.date", FixedDate)

    summary = cost_summary_from_db(db, sub, timeframe="MonthToDate")
    assert summary is None
    db.close()


def test_ytd_uses_stored_period_total_from_cost_management(monkeypatch):
    """YTD must use the hourly-synced Cost Management subscription total, not partial aggregates."""
    from datetime import date

    from app.cost_period_totals import upsert_period_total
    from app.models import CostByServiceSnapshot

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    sub = "sub-1"
    db.add(
        CostByServiceSnapshot(
            id="svc-jul",
            subscription_id=sub,
            service_name="Virtual Machines",
            month="2026-07",
            cost_usd=168823.0,
            cost_billing=168823.0,
            billing_currency="CAD",
        )
    )
    db.commit()

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 6)

    monkeypatch.setattr("app.cost_timeframes.date", FixedDate)

    upsert_period_total(
        db,
        sub,
        "ThisYear",
        period_start="2026-01-01",
        period_end="2026-07-06",
        pretax_total=776170.0,
        cost_usd_total=600000.0,
        billing_currency="CAD",
    )
    db.commit()

    summary = cost_summary_from_db(db, sub, timeframe="ThisYear")
    assert summary is not None
    assert summary["pretax_total"] == 776170.0
    assert summary["total_source"] == "azure_subscription_query"
    assert summary["period_start"] == "2026-01-01"
    assert summary["period_end"] == "2026-07-06"
    db.close()


def test_last30days_uses_stored_period_total(monkeypatch):
    """Rolling windows must use hourly-synced Cost Management totals."""
    from datetime import date

    from app.cost_period_totals import upsert_period_total

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    sub = "sub-1"

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 6)

    monkeypatch.setattr("app.cost_timeframes.date", FixedDate)

    upsert_period_total(
        db,
        sub,
        "Last30Days",
        period_start="2026-06-07",
        period_end="2026-07-06",
        pretax_total=125000.0,
        cost_usd_total=100000.0,
        billing_currency="CAD",
    )
    db.commit()

    summary = cost_summary_from_db(db, sub, timeframe="Last30Days")
    assert summary is not None
    assert summary["pretax_total"] == 125000.0
    assert summary["period_start"] == "2026-06-07"
    assert summary["period_end"] == "2026-07-06"
    db.close()


def test_mtd_uses_stored_period_total(monkeypatch):
    from datetime import date

    from app.cost_period_totals import upsert_period_total

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    sub = "sub-1"

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 6)

    monkeypatch.setattr("app.cost_timeframes.date", FixedDate)

    upsert_period_total(
        db,
        sub,
        "MonthToDate",
        period_start="2026-07-01",
        period_end="2026-07-06",
        pretax_total=42000.0,
        cost_usd_total=33600.0,
        billing_currency="CAD",
    )
    db.commit()

    summary = cost_summary_from_db(db, sub, timeframe="MonthToDate")
    assert summary is not None
    assert summary["pretax_total"] == 42000.0
    db.close()


def test_ytd_prefers_subscription_sync_run_over_inflated_service_sum(monkeypatch):
    """YTD must use authoritative subscription totals, not inflated per-service sums."""
    from datetime import date

    from app.models import CostDailyByServiceSnapshot

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    sub = "sub-1"
    db.add(
        CostSyncRun(
            id="run-jan",
            subscription_id=sub,
            month="2026-01",
            mtd_start="2026-01-01",
            mtd_end="2026-01-31",
            total_billing=6000.0,
            total_usd=4800.0,
            billing_currency="CAD",
            services_json="[]",
            changes_json="[]",
            synced_at=datetime(2026, 1, 31, 12, 0, tzinfo=timezone.utc),
        )
    )
    db.add(
        CostByServiceSnapshot(
            id="svc-jan",
            subscription_id=sub,
            service_name="Virtual Machines",
            month="2026-01",
            cost_usd=9000.0,
            cost_billing=10000.0,
            billing_currency="CAD",
        )
    )
    db.add(
        CostSyncRun(
            id="run-jul",
            subscription_id=sub,
            month="2026-07",
            mtd_start="2026-07-01",
            mtd_end="2026-07-06",
            total_billing=2000.0,
            total_usd=1600.0,
            billing_currency="CAD",
            services_json="[]",
            changes_json="[]",
            synced_at=datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc),
        )
    )
    db.commit()

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 6)

    monkeypatch.setattr("app.cost_timeframes.date", FixedDate)

    summary = cost_summary_from_db(db, sub, timeframe="ThisYear")
    assert summary is not None
    assert summary["pretax_total"] == 8000.0
    assert summary["total_source"] == "multi_month_aggregate"
    db.close()


def test_ytd_uses_daily_subscription_rollup_for_closed_month_without_sync_run(monkeypatch):
    """Closed months without sync runs should aggregate daily subscription rollup rows."""
    from datetime import date

    from app.models import CostDailyByServiceSnapshot

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    sub = "sub-1"
    for day, amount in [("2026-01-10", 400.0), ("2026-01-20", 600.0)]:
        db.add(
            CostDailyByServiceSnapshot(
                id=f"daily-jan-{day}",
                subscription_id=sub,
                cost_date=day,
                service_name="__subscription__",
                cost_billing=amount,
                cost_usd=amount * 0.8,
                billing_currency="CAD",
            )
        )
    db.add(
        CostSyncRun(
            id="run-jul",
            subscription_id=sub,
            month="2026-07",
            mtd_start="2026-07-01",
            mtd_end="2026-07-02",
            total_billing=300.0,
            total_usd=240.0,
            billing_currency="CAD",
            services_json="[]",
            changes_json="[]",
            synced_at=datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
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
    assert summary["pretax_total"] == 1300.0
    db.close()


def test_cost_summary_last30days_sums_daily_rows_not_mtd_sync(monkeypatch):
    """Rolling 30-day windows must aggregate daily rows, not MTD sync-run totals."""
    from datetime import date

    from app.models import CostDailyByServiceSnapshot, CostSyncRun

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    sub = "sub-1"
    month = "2026-07"
    db.add(
        CostSyncRun(
            id="run-1",
            subscription_id=sub,
            month=month,
            mtd_start="2026-07-01",
            mtd_end="2026-07-06",
            total_billing=6000.0,
            total_usd=4800.0,
            billing_currency="CAD",
            services_json="[]",
            changes_json="[]",
            synced_at=datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc),
        )
    )
    for day, amount in [("2026-06-10", 50.0), ("2026-06-20", 75.0), ("2026-07-02", 100.0)]:
        db.add(
            CostDailyByServiceSnapshot(
                id=f"daily-{day}",
                subscription_id=sub,
                cost_date=day,
                service_name="__subscription__",
                cost_billing=amount,
                cost_usd=amount * 0.8,
                billing_currency="CAD",
            )
        )
    db.commit()

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 6)

    monkeypatch.setattr("app.cost_timeframes.date", FixedDate)

    mtd = cost_summary_from_db(db, sub, timeframe="MonthToDate")
    rolling = cost_summary_from_db(db, sub, timeframe="Last30Days")
    assert mtd is not None
    assert mtd["pretax_total"] == 6000.0
    assert rolling is not None
    assert rolling["pretax_total"] == 225.0
    assert rolling["total_source"] == "daily_rows_sum"
    assert rolling["period_start"] == "2026-06-07"
    assert rolling["period_end"] == "2026-07-06"
    db.close()


def test_cost_summary_falls_back_to_resource_snapshots(monkeypatch):
    from datetime import date

    from app.models import CostByResourceSnapshot

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    sub = "sub-1"
    month = "2026-07"

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 15)

    monkeypatch.setattr("app.cost_timeframes.date", FixedDate)

    db.add(
        CostByResourceSnapshot(
            id="res-1",
            subscription_id=sub,
            resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm-1",
            resource_type="microsoft.compute/virtualmachines",
            resource_group="rg",
            service_name="Virtual Machines",
            month=month,
            cost_billing=880.0,
            cost_usd=700.0,
            billing_currency="CAD",
        )
    )
    db.commit()

    summary = cost_summary_from_db(db, sub, timeframe="MonthToDate")
    assert summary is not None
    assert summary["pretax_total"] == 880.0
    assert summary["total_source"] == "resource_rows_sum"
    db.close()
