"""Engine analysis API — advisor summary field mapping."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import AdvisorRecommendation, Base
from app.routers.engine_analysis import _advisor_summary


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_advisor_summary_uses_model_summary_field(db_session):
    sub = "sub-1"
    db_session.add(AdvisorRecommendation(
        id=str(uuid.uuid4()),
        recommendation_id="rec-001",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        subscription_id=sub,
        category="Cost",
        impact="High",
        summary="Underutilized virtual machine",
        description="Resize or shut down the VM to save cost.",
        potential_savings_monthly=120.0,
        status="Active",
        generated_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    result = _advisor_summary(db_session, sub)

    assert result["total"] == 1
    item = result["by_category"]["cost"]["items"][0]
    assert item["summary"] == "Underutilized virtual machine"
    assert item["short_description"] == "Underutilized virtual machine"
    assert item["description"] == "Resize or shut down the VM to save cost."
    assert item["potential_savings_monthly"] == 120.0
