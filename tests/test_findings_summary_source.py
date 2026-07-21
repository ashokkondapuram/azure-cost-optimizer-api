"""Source breakdown and Action centre counts for findings summary."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import migrate_schema
from app.findings_summary import build_findings_summary, classify_finding_source
from app.focus_mapping import normalize_arm_id
from app.models import Base, OptimizationFinding, ResourceSnapshot

SUB = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
INV_ID = (
    f"/subscriptions/{SUB}/resourceGroups/rg-live/providers/"
    "Microsoft.Compute/virtualMachines/vm-live"
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    migrate_schema()
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _add_inventory(db):
    db.add(
        ResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=SUB,
            resource_id=normalize_arm_id(INV_ID),
            resource_name="vm-live",
            resource_type="compute/vm",
            resource_group="rg-live",
            location="canadacentral",
            state="running",
            properties_json='{"provisioningState":"Succeeded"}',
            tags_json="{}",
            sku_json="{}",
            is_active=True,
            synced_at=datetime.now(timezone.utc),
        )
    )


def test_classify_finding_source_buckets():
    assert classify_finding_source(
        OptimizationFinding(rule_id="advisor_rec-1", category="RELIABILITY")
    ) == "reliability_security"
    assert classify_finding_source(
        OptimizationFinding(
            rule_id="VM_IDLE",
            category="COMPUTE",
            evidence_json='{"engine": "azure_advisor"}',
        )
    ) == "reliability_security"
    assert classify_finding_source(
        OptimizationFinding(rule_id="GOVERNANCE_TAG_ENFORCEMENT", category="GOVERNANCE")
    ) == "governance"
    assert classify_finding_source(
        OptimizationFinding(rule_id="DISK_OVERSIZE", category="STORAGE")
    ) == "cost_performance"


def test_build_findings_summary_by_source_sums_to_action_centre_total(db):
    _add_inventory(db)
    db.add_all([
        OptimizationFinding(
            id="f-cost",
            subscription_id=SUB,
            resource_id=normalize_arm_id(INV_ID),
            status="open",
            severity="HIGH",
            category="COMPUTE",
            rule_id="VM_IDLE",
        ),
        OptimizationFinding(
            id="f-advisor",
            subscription_id=SUB,
            resource_id=normalize_arm_id(INV_ID),
            status="open",
            severity="MEDIUM",
            category="RELIABILITY",
            rule_id="advisor_rec-ha",
        ),
        OptimizationFinding(
            id="f-gov",
            subscription_id=SUB,
            resource_id=normalize_arm_id(INV_ID),
            status="open",
            severity="LOW",
            category="GOVERNANCE",
            rule_id="GOVERNANCE_TAG_ENFORCEMENT",
        ),
        OptimizationFinding(
            id="f-metric",
            subscription_id=SUB,
            resource_id=normalize_arm_id(INV_ID),
            status="open",
            severity="INFO",
            category="METRIC",
            rule_id="metric_transactions_missing",
        ),
    ])
    db.commit()

    summary = build_findings_summary(db, SUB)

    assert summary["open_findings"] == 3
    assert summary["open_findings_all"] == 4
    assert summary["excluded"]["metric_gaps"] == 1
    assert summary["by_source"]["cost_performance"] == 1
    assert summary["by_source"]["reliability_security"] == 1
    assert summary["by_source"]["governance"] == 1
    assert sum(summary["by_source"].values()) == summary["open_findings"]
    assert summary["resources_with_findings"] == 1
