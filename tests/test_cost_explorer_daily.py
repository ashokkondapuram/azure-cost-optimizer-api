"""Tests for daily subscription cost persistence."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.cost_db import daily_cost_response_from_db, mtd_period_for_timeframe
from app.cost_explorer_sync import _replace_daily_subscription_costs
from app.models import Base


def test_replace_daily_subscription_costs_populates_daily_chart():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    period = mtd_period_for_timeframe("MonthToDate")
    mtd_start = period["mtd_start"]
    mtd_end = period["mtd_end"]
    start = date.fromisoformat(mtd_start)
    end = date.fromisoformat(mtd_end)
    dates: list[str] = []
    cursor = start
    while cursor <= end and len(dates) < 2:
        dates.append(cursor.isoformat())
        cursor += timedelta(days=1)

    sub = "sub-1"
    rows = [
        {"date": d, "cost": 100.0 * (i + 1), "cost_usd": 80.0 * (i + 1), "currency": "CAD"}
        for i, d in enumerate(dates)
    ]
    written = _replace_daily_subscription_costs(
        db,
        sub,
        rows,
        mtd_start=mtd_start,
        mtd_end=mtd_end,
    )
    db.commit()
    assert written == len(dates)

    daily = daily_cost_response_from_db(db, sub, timeframe="MonthToDate")
    assert daily is not None
    props = daily["properties"]
    assert len(props["rows"]) == len(dates)
    assert props["rows"][0][3] == dates[0]
    assert props["rows"][0][0] == rows[0]["cost"]
    db.close()
