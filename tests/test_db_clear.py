"""Tests for database clear helpers."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db_clear import clear_database
from app.models import (
    AppUser,
    Base,
    CustomBudget,
    EngineConfig,
    OptimizationFinding,
    ResourceSnapshot,
    SystemSetting,
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _seed_subscription_rows(db_session, subscription_id: str = "sub-clear-test"):
    suffix = subscription_id.replace("/", "-")
    db_session.add(ResourceSnapshot(
        id=f"res-{suffix}",
        subscription_id=subscription_id,
        resource_id=f"/subscriptions/{subscription_id}/resourceGroups/rg/providers/Microsoft.Compute/disks/d1",
        resource_name="disk-1",
        resource_type="Microsoft.Compute/disks",
        resource_group="rg",
        location="eastus",
        properties_json="{}",
    ))
    db_session.add(OptimizationFinding(
        id=f"finding-{suffix}",
        run_id=f"run-{suffix}",
        rule_id="RULE_1",
        subscription_id=subscription_id,
        resource_id=f"/subscriptions/{subscription_id}/resourceGroups/rg/providers/Microsoft.Compute/disks/d1",
        severity="medium",
        category="cost",
    ))
    db_session.add(CustomBudget(
        id=f"budget-{suffix}",
        subscription_id=subscription_id,
        name="Test budget",
        monthly_limit=1000.0,
    ))
    db_session.commit()


def test_clear_synced_data_scoped_to_subscription(db_session):
    _seed_subscription_rows(db_session, "sub-a")
    _seed_subscription_rows(db_session, "sub-b")

    result = clear_database(db_session, subscription_id="sub-a", mode="synced")

    assert result["mode"] == "synced"
    assert db_session.query(ResourceSnapshot).filter_by(subscription_id="sub-a").count() == 0
    assert db_session.query(ResourceSnapshot).filter_by(subscription_id="sub-b").count() == 1
    assert db_session.query(CustomBudget).filter_by(subscription_id="sub-a").count() == 0
    assert db_session.query(CustomBudget).filter_by(subscription_id="sub-b").count() == 1
    assert "app_users" in result["preserved_tables"]
    assert result["deleted"]["resource_snapshots"] == 1


def test_clear_synced_data_all_subscriptions(db_session):
    _seed_subscription_rows(db_session, "sub-a")
    _seed_subscription_rows(db_session, "sub-b")

    result = clear_database(db_session, mode="synced")

    assert db_session.query(ResourceSnapshot).count() == 0
    assert db_session.query(OptimizationFinding).count() == 0
    assert result["deleted"]["resource_snapshots"] == 2


def test_clear_all_tables_wipes_users_and_settings(db_session):
    _seed_subscription_rows(db_session)
    db_session.add(AppUser(
        id="user-1",
        username="tester",
        password_hash="hash",
        role="admin",
    ))
    db_session.add(SystemSetting(
        id="settings-1",
        category="azure",
        config_json="{}",
    ))
    db_session.add(EngineConfig(
        id="engine-1",
        rule_id="RULE_TEST",
        profile="default",
    ))
    db_session.commit()

    result = clear_database(db_session, mode="all")

    assert result["mode"] == "all"
    assert result["preserved_tables"] == []
    assert db_session.query(ResourceSnapshot).count() == 0
    assert db_session.query(AppUser).count() == 0
    assert db_session.query(SystemSetting).count() == 0
    assert db_session.query(EngineConfig).count() == 0
