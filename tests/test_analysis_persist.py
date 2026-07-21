"""Tests for optimization finding persistence (upsert behavior)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.analysis_persist import persist_optimization_run
from app.models import Base, OptimizationFinding


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _finding_payload(
    *,
    resource_id: str,
    rule_id: str = "VM_COMMITMENT_CANDIDATE",
    savings: float = 22.0,
) -> dict:
    return {
        "rule_id": rule_id,
        "rule_name": "Reserved Instance or Savings Plan Candidate",
        "category": "COST",
        "severity": "MEDIUM",
        "resource_id": resource_id,
        "resource_name": "vmss1",
        "resource_type": "compute/vmss",
        "resource_group": "rg",
        "location": "eastus",
        "detail": "Evaluate Reservations or Savings Plans.",
        "recommendation": "Group always-on compute by family and region.",
        "estimated_savings_usd": savings,
        "evidence": {"vm_size": "Standard_D4s_v3"},
    }


def _insert_open_finding(
    db,
    *,
    resource_id: str,
    finding_id: str | None = None,
    rule_id: str = "VM_COMMITMENT_CANDIDATE",
) -> OptimizationFinding:
    row = OptimizationFinding(
        id=finding_id or str(uuid.uuid4()),
        run_id="run-old",
        rule_id=rule_id,
        rule_name="Reserved Instance or Savings Plan Candidate",
        category="COST",
        severity="MEDIUM",
        resource_id=resource_id,
        resource_name="vmss1",
        resource_type="compute/vmss",
        subscription_id="sub-a",
        resource_group="rg",
        location="eastus",
        detail="Old detail",
        recommendation="Old recommendation",
        estimated_savings_usd=22.0,
        status="open",
        detected_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return row


def _result(findings: list[dict]) -> dict:
    return {
        "findings": findings,
        "summary": {
            "total_findings": len(findings),
            "by_severity": {"MEDIUM": len(findings)},
            "total_estimated_monthly_savings_usd": sum(
                f.get("estimated_savings_usd") or 0 for f in findings
            ),
        },
    }


def test_persist_upserts_existing_open_finding(db_session):
    rid = "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/vmss1"
    existing = _insert_open_finding(db_session, resource_id=rid)
    payload = _finding_payload(resource_id=rid, savings=25.0)

    persist_optimization_run(
        db_session,
        subscription_id="sub-a",
        profile="default",
        engine_version="extended",
        result=_result([payload]),
    )

    open_rows = (
        db_session.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == "sub-a",
            OptimizationFinding.status == "open",
            OptimizationFinding.rule_id == "VM_COMMITMENT_CANDIDATE",
        )
        .all()
    )
    assert len(open_rows) == 1
    assert open_rows[0].estimated_savings_usd == 25.0
    assert open_rows[0].detail == payload["detail"]

    db_session.refresh(existing)
    assert existing.status == "resolved"


def test_persist_collapses_duplicate_open_rows_for_same_resource_rule(db_session):
    base = "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/vmss1"
    dup_a = _insert_open_finding(db_session, resource_id=base)
    dup_b = _insert_open_finding(db_session, resource_id=base.lower())
    dup_c = _insert_open_finding(
        db_session,
        resource_id=f"{base}/",
    )

    persist_optimization_run(
        db_session,
        subscription_id="sub-a",
        profile="default",
        engine_version="extended",
        result=_result([_finding_payload(resource_id=base)]),
    )

    open_rows = (
        db_session.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == "sub-a",
            OptimizationFinding.rule_id == "VM_COMMITMENT_CANDIDATE",
            OptimizationFinding.status == "open",
        )
        .all()
    )
    resolved_rows = (
        db_session.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == "sub-a",
            OptimizationFinding.rule_id == "VM_COMMITMENT_CANDIDATE",
            OptimizationFinding.status == "resolved",
        )
        .all()
    )
    assert len(open_rows) == 1
    assert open_rows[0].id not in {dup_a.id, dup_b.id, dup_c.id}
    assert len(resolved_rows) == 3


def test_persist_resolves_stale_open_findings_not_in_run(db_session):
    stale_rid = "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-old"
    _insert_open_finding(
        db_session,
        resource_id=stale_rid,
    )
    active_rid = "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/vmss1"

    persist_optimization_run(
        db_session,
        subscription_id="sub-a",
        profile="default",
        engine_version="extended",
        result=_result([_finding_payload(resource_id=active_rid)]),
    )

    stale = (
        db_session.query(OptimizationFinding)
        .filter(OptimizationFinding.resource_id == stale_rid.lower())
        .first()
    )
    assert stale is not None
    assert stale.status == "resolved"

    open_count = (
        db_session.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == "sub-a",
            OptimizationFinding.status == "open",
        )
        .count()
    )
    assert open_count == 1


def test_persist_second_run_replaces_prior_open_row(db_session):
    rid = "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/vmss1"
    persist_optimization_run(
        db_session,
        subscription_id="sub-a",
        profile="default",
        engine_version="extended",
        result=_result([_finding_payload(resource_id=rid, savings=20.0)]),
    )
    first_open = (
        db_session.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == "sub-a",
            OptimizationFinding.status == "open",
            OptimizationFinding.rule_id == "VM_COMMITMENT_CANDIDATE",
        )
        .one()
    )
    persist_optimization_run(
        db_session,
        subscription_id="sub-a",
        profile="default",
        engine_version="extended",
        result=_result([_finding_payload(resource_id=rid, savings=30.0)]),
    )

    open_rows = (
        db_session.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == "sub-a",
            OptimizationFinding.status == "open",
            OptimizationFinding.rule_id == "VM_COMMITMENT_CANDIDATE",
        )
        .all()
    )
    assert len(open_rows) == 1
    assert open_rows[0].id != first_open.id
    assert open_rows[0].estimated_savings_usd == 30.0

    db_session.refresh(first_open)
    assert first_open.status == "resolved"


def test_persist_upserts_when_subscription_id_casing_differs(db_session):
    rid = "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/vmss1"
    existing = _insert_open_finding(db_session, resource_id=rid)
    existing.subscription_id = "SUB-A"
    db_session.commit()

    persist_optimization_run(
        db_session,
        subscription_id="sub-a",
        profile="default",
        engine_version="extended",
        result=_result([_finding_payload(resource_id=rid, savings=28.0)]),
    )

    open_rows = (
        db_session.query(OptimizationFinding)
        .filter(
            OptimizationFinding.status == "open",
            OptimizationFinding.rule_id == "VM_COMMITMENT_CANDIDATE",
        )
        .all()
    )
    assert len(open_rows) == 1
    assert open_rows[0].subscription_id == "sub-a"
    assert open_rows[0].estimated_savings_usd == 28.0

    db_session.refresh(existing)
    assert existing.status == "resolved"


def test_persist_scoped_run_updates_existing_open_row(db_session):
    rid = "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/vmss1"
    existing = _insert_open_finding(db_session, resource_id=rid)

    persist_optimization_run(
        db_session,
        subscription_id="sub-a",
        profile="default",
        engine_version="extended",
        result=_result([_finding_payload(resource_id=rid, savings=28.0)]),
        scope_resource_types={"compute/vmss"},
    )

    open_rows = (
        db_session.query(OptimizationFinding)
        .filter(
            OptimizationFinding.status == "open",
            OptimizationFinding.rule_id == "VM_COMMITMENT_CANDIDATE",
        )
        .all()
    )
    assert len(open_rows) == 1
    assert open_rows[0].id == existing.id
    assert open_rows[0].estimated_savings_usd == 28.0


def test_supersede_open_findings_resolves_all_open(db_session):
    from app.analysis_persist import supersede_open_findings

    _insert_open_finding(db_session, resource_id="/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1")
    _insert_open_finding(db_session, resource_id="/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm2")

    count = supersede_open_findings(db_session, "sub-a", commit=True)
    assert count == 2
    open_count = (
        db_session.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == "sub-a",
            OptimizationFinding.status == "open",
        )
        .count()
    )
    assert open_count == 0


def test_dedupe_open_findings_for_display_keeps_latest(db_session):
    from app.analysis_persist import dedupe_open_findings_for_display

    rid = "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/vmss1"
    older = _insert_open_finding(db_session, resource_id=rid)
    newer = _insert_open_finding(db_session, resource_id=rid.lower())

    rows = dedupe_open_findings_for_display([older, newer])
    assert len(rows) == 1


def test_dedupe_open_findings_for_display_collapses_trailing_slash(db_session):
    from app.analysis_persist import dedupe_open_findings_for_display

    rid = "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Network/applicationGateways/agw1"
    first = _insert_open_finding(
        db_session,
        resource_id=rid,
        rule_id="COST_HIGH_SPEND_REVIEW",
    )
    first.rule_id = "COST_HIGH_SPEND_REVIEW"
    first.rule_name = "High monthly spend review"
    second = _insert_open_finding(
        db_session,
        resource_id=f"{rid}/",
        rule_id="COST_HIGH_SPEND_REVIEW",
    )
    second.rule_id = "COST_HIGH_SPEND_REVIEW"
    second.rule_name = "High monthly spend review"
    db_session.commit()

    rows = dedupe_open_findings_for_display([first, second])
    assert len(rows) == 1


def test_cleanup_duplicate_open_findings_resolves_rows(db_session):
    from app.analysis_persist import cleanup_duplicate_open_findings

    rid = "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Network/applicationGateways/agw1"
    _insert_open_finding(db_session, resource_id=rid, rule_id="COST_HIGH_SPEND_REVIEW")
    _insert_open_finding(db_session, resource_id=f"{rid}/", rule_id="COST_HIGH_SPEND_REVIEW")

    resolved = cleanup_duplicate_open_findings(db_session, "sub-a")
    assert resolved == 1
    open_rows = (
        db_session.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == "sub-a",
            OptimizationFinding.status == "open",
            OptimizationFinding.rule_id == "COST_HIGH_SPEND_REVIEW",
        )
        .all()
    )
    assert len(open_rows) == 1
