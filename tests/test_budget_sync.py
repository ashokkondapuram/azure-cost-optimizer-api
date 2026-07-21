"""Tests for Azure budget snapshot sync."""

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.budget_sync import _parse_azure_budget, sync_budget_snapshots
from app.models import Base, BudgetSnapshot


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_parse_azure_budget_extracts_amounts():
    parsed = _parse_azure_budget(
        {
            "name": "prod-monthly",
            "properties": {
                "amount": 10000,
                "timeGrain": "Monthly",
                "currentSpend": {"amount": 2500},
                "forecastSpend": {"amount": 4200},
                "currency": "CAD",
            },
        },
        "sub-1",
    )
    assert parsed["budget_name"] == "prod-monthly"
    assert parsed["amount"] == 10000
    assert parsed["current_spend"] == 2500
    assert parsed["forecast_spend"] == 4200


def test_sync_budget_snapshots_replaces_rows(db_session, monkeypatch):
    client = MagicMock()
    client.list_budgets.return_value = [
        {
            "name": "team-budget",
            "properties": {
                "amount": 5000,
                "timeGrain": "Monthly",
                "currentSpend": {"amount": 1200},
                "forecastSpend": {"amount": 1800},
                "currency": "CAD",
            },
        }
    ]
    monkeypatch.setattr("app.azure_cost.AzureCostClient", lambda db, token: client)

    count = sync_budget_snapshots("sub-1", db_session, "token")
    db_session.commit()

    assert count == 1
    rows = db_session.query(BudgetSnapshot).filter(BudgetSnapshot.subscription_id == "sub-1").all()
    assert len(rows) == 1
    assert rows[0].budget_name == "team-budget"
    assert rows[0].current_spend == 1200

    client.list_budgets.return_value = []
    sync_budget_snapshots("sub-1", db_session, "token")
    db_session.commit()
    assert db_session.query(BudgetSnapshot).filter(BudgetSnapshot.subscription_id == "sub-1").count() == 0
