"""Tests for idle resource sweep and waste heatmap rule matching."""

import uuid

from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.idle_resource_rules import is_idle_or_waste_rule
from app.main import app
from app.models import AppUser, OptimizationFinding
from app.user_auth import ROLE_ADMIN, hash_password

SUBSCRIPTION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _seed_findings(findings: list[OptimizationFinding]) -> None:
    init_db()
    db = SessionLocal()
    try:
        db.query(OptimizationFinding).delete()
        for row in findings:
            db.add(row)
        db.commit()
    finally:
        db.close()


def _auth_client() -> TestClient:
    init_db()
    db = SessionLocal()
    try:
        db.query(AppUser).filter(AppUser.username == "admin").delete()
        db.commit()
        db.add(
            AppUser(
                id="admin-idle-sweep",
                username="admin",
                display_name="Administrator",
                password_hash=hash_password("password123"),
                role=ROLE_ADMIN,
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "admin", "password": "password123"})
    token = login.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_is_idle_or_waste_rule_matches_real_engine_ids():
    assert is_idle_or_waste_rule("VM_IDLE")
    assert is_idle_or_waste_rule("DISK_UNATTACHED")
    assert is_idle_or_waste_rule("PUBLIC_IP_IDLE_EXTENDED")
    assert is_idle_or_waste_rule("REDIS_IDLE_DETECTION")
    assert is_idle_or_waste_rule("REDIS_LOW_UTILIZATION")
    assert is_idle_or_waste_rule("POSTGRESQL_STOPPED_EXTENDED")
    assert is_idle_or_waste_rule("POSTGRESQL_LOW_COMPUTE_UTILIZATION")
    assert not is_idle_or_waste_rule("COSMOS_RU_RIGHT_SIZING_UNDER")
    assert not is_idle_or_waste_rule("COSMOS_RESERVED_CAPACITY_ELIGIBLE")
    assert not is_idle_or_waste_rule("BUDGET_WARNING")
    assert not is_idle_or_waste_rule("")


def test_idle_resource_sweep_returns_matching_findings():
    _seed_findings([
        OptimizationFinding(
            id=str(uuid.uuid4()),
            run_id="run-1",
            rule_id="VM_IDLE",
            rule_name="Idle VM",
            category="COMPUTE",
            severity="HIGH",
            resource_id="/subscriptions/aaa/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
            resource_name="vm1",
            resource_type="compute/vm",
            subscription_id=SUBSCRIPTION_ID,
            detail="Idle",
            recommendation="Stop",
            estimated_savings_usd=120.0,
            status="open",
        ),
        OptimizationFinding(
            id=str(uuid.uuid4()),
            run_id="run-1",
            rule_id="BUDGET_WARNING",
            rule_name="Budget warning",
            category="COST",
            severity="HIGH",
            resource_id="",
            resource_name="",
            resource_type="",
            subscription_id=SUBSCRIPTION_ID,
            detail="Budget",
            recommendation="Review",
            estimated_savings_usd=10.0,
            status="open",
        ),
    ])

    client = _auth_client()
    response = client.get(f"/api/idle-resources/sweep/{SUBSCRIPTION_ID}")
    assert response.status_code == 200
    body = response.json()
    assert body["total_idle_findings"] == 1
    assert body["total_estimated_savings_usd"] == 120.0
    assert body["findings_with_savings"] == 1
    assert body["items_returned"] == 1
    assert body["items_truncated"] is False
    assert "heatmap_matrix" in body
    assert body["idle_resources"][0]["rule_id"] == "VM_IDLE"
    assert body["idle_resources"][0]["category"] == "Compute"
    assert body["idle_resources"][0]["severity"] == "high"
    assert body["idle_resources"][0]["title"] == "Idle VM"


def test_idle_resource_sweep_includes_database_waste_rules():
    _seed_findings([
        OptimizationFinding(
            id=str(uuid.uuid4()),
            run_id="run-1",
            rule_id="REDIS_LOW_UTILIZATION",
            rule_name="Redis low utilization",
            category="DATABASE",
            severity="MEDIUM",
            resource_id="/subscriptions/aaa/resourcegroups/rg/providers/microsoft.cache/redis/redis1",
            resource_name="redis1",
            resource_type="database/redis",
            subscription_id=SUBSCRIPTION_ID,
            detail="Low ops",
            recommendation="Downgrade tier",
            estimated_savings_usd=45.0,
            status="open",
        ),
        OptimizationFinding(
            id=str(uuid.uuid4()),
            run_id="run-1",
            rule_id="POSTGRESQL_STOPPED_EXTENDED",
            rule_name="Stopped PostgreSQL",
            category="DATABASE",
            severity="HIGH",
            resource_id="/subscriptions/aaa/resourcegroups/rg/providers/microsoft.dbforpostgresql/flexibleservers/pg1",
            resource_name="pg1",
            resource_type="database/postgresql",
            subscription_id=SUBSCRIPTION_ID,
            detail="Stopped",
            recommendation="Delete",
            estimated_savings_usd=80.0,
            status="open",
        ),
        OptimizationFinding(
            id=str(uuid.uuid4()),
            run_id="run-1",
            rule_id="COSMOS_RU_RIGHT_SIZING_UNDER",
            rule_name="Cosmos RU rightsize",
            category="DATABASE",
            severity="MEDIUM",
            resource_id="/subscriptions/aaa/resourcegroups/rg/providers/microsoft.documentdb/databaseaccounts/cosmos1",
            resource_name="cosmos1",
            resource_type="database/cosmosdb",
            subscription_id=SUBSCRIPTION_ID,
            detail="Low RU",
            recommendation="Reduce throughput",
            estimated_savings_usd=30.0,
            status="open",
        ),
    ])

    client = _auth_client()
    response = client.get(f"/api/idle-resources/sweep/{SUBSCRIPTION_ID}")
    assert response.status_code == 200
    body = response.json()
    assert body["total_idle_findings"] == 2
    assert body["by_category"]["Database"] == 2
    rule_ids = {row["rule_id"] for row in body["idle_resources"]}
    assert rule_ids == {"REDIS_LOW_UTILIZATION", "POSTGRESQL_STOPPED_EXTENDED"}


def test_idle_resource_summary_groups_by_rule():
    _seed_findings([
        OptimizationFinding(
            id=str(uuid.uuid4()),
            run_id="run-1",
            rule_id="DISK_UNATTACHED",
            rule_name="Unattached disk",
            category="COMPUTE",
            severity="HIGH",
            resource_id="/subscriptions/aaa/resourcegroups/rg/providers/microsoft.compute/disks/d1",
            resource_name="d1",
            resource_type="compute/disk",
            subscription_id=SUBSCRIPTION_ID,
            detail="Unattached",
            recommendation="Delete",
            estimated_savings_usd=40.0,
            status="open",
        ),
    ])

    client = _auth_client()
    response = client.get(f"/api/idle-resources/summary/{SUBSCRIPTION_ID}")
    assert response.status_code == 200
    body = response.json()
    assert body["total_idle_findings"] == 1
    assert body["top_rules"][0]["rule_id"] == "DISK_UNATTACHED"
    assert body["top_rules"][0]["title"] == "Unattached disk"
    assert body["most_common_rule"]["rule_id"] == "DISK_UNATTACHED"
