"""Tests for persisted custom budgets."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.budget_custom_store import (
    create_custom_budget,
    delete_custom_budget,
    list_custom_budgets,
    update_custom_budget,
)
from app.models import Base


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_custom_budget_crud_round_trip(db_session):
    created = create_custom_budget(db_session, {
        "subscription_id": "sub-1",
        "name": "Dev budget",
        "monthly_limit": 3000,
        "scope": "resource-group",
        "alert_thresholds": [70, 90],
    })
    db_session.commit()

    assert created["name"] == "Dev budget"
    rows = list_custom_budgets(db_session, "sub-1")
    assert len(rows) == 1
    assert rows[0]["monthly_limit"] == 3000

    updated = update_custom_budget(db_session, "sub-1", "Dev budget", {"monthly_limit": 3500})
    db_session.commit()
    assert updated["monthly_limit"] == 3500

    assert delete_custom_budget(db_session, "sub-1", "Dev budget")
    db_session.commit()
    assert list_custom_budgets(db_session, "sub-1") == []
