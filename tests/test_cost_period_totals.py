"""Tests for hourly-synced Cost Management period totals."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.cost_period_totals import period_total_from_db, upsert_period_total
from app.models import Base, CostPeriodTotalSnapshot


def test_upsert_period_total_replaces_existing_row():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    sub = "sub-1"
    upsert_period_total(
        db,
        sub,
        "ThisYear",
        period_start="2026-01-01",
        period_end="2026-07-01",
        pretax_total=100000.0,
        cost_usd_total=80000.0,
        billing_currency="CAD",
    )
    db.commit()
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

    rows = db.query(CostPeriodTotalSnapshot).filter(CostPeriodTotalSnapshot.subscription_id == sub).all()
    assert len(rows) == 1
    assert rows[0].pretax_total == 776170.0
    assert rows[0].period_end == "2026-07-06"

    summary = period_total_from_db(db, sub, "ThisYear", period_end="2026-07-06")
    assert summary is not None
    assert summary["pretax_total"] == 776170.0
    db.close()


def test_period_total_allows_same_month_stale_period_end():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    sub = "sub-1"
    upsert_period_total(
        db,
        sub,
        "MonthToDate",
        period_start="2026-07-01",
        period_end="2026-07-14",
        pretax_total=12000.0,
        cost_usd_total=9600.0,
        billing_currency="CAD",
    )
    db.commit()

    summary = period_total_from_db(
        db,
        sub,
        "MonthToDate",
        period_start="2026-07-01",
        period_end="2026-07-15",
    )
    assert summary is not None
    assert summary["pretax_total"] == 12000.0
    db.close()
