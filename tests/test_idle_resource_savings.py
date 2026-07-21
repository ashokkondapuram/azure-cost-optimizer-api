"""Tests for idle resource savings resolution."""

import json
import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.idle_resource_rules import resolve_finding_savings_usd
from app.integration_app import app
from app.models import AppUser, CostByResourceSnapshot, OptimizationFinding
from app.user_auth import ROLE_ADMIN, hash_password


def _finding(**kwargs):
    return SimpleNamespace(**kwargs)


def test_resolve_finding_savings_prefers_stored_value():
    f = _finding(estimated_savings_usd=42.0, evidence_json="{}")
    assert resolve_finding_savings_usd(f) == (42.0, "stored")


def test_resolve_finding_savings_from_evidence_monthly_cost():
    evidence = json.dumps({"monthly_cost_usd": 18.5})
    f = _finding(estimated_savings_usd=0, evidence_json=evidence)
    assert resolve_finding_savings_usd(f) == (18.5, "evidence_cost")


def test_resolve_finding_savings_from_resource_cost_fallback():
    f = _finding(estimated_savings_usd=0, evidence_json="{}")
    assert resolve_finding_savings_usd(f, resource_cost_usd=25.0) == (25.0, "resource_cost")


def test_resolve_finding_savings_from_annualized():
    f = _finding(estimated_savings_usd=0, annualized_savings_usd=120.0, evidence_json="{}")
    assert resolve_finding_savings_usd(f) == (10.0, "stored")


def test_resolve_finding_savings_from_retail_evidence():
    evidence = json.dumps({"retail_monthly_savings_usd": 55.0})
    f = _finding(estimated_savings_usd=0, evidence_json=evidence)
    assert resolve_finding_savings_usd(f) == (55.0, "evidence")


def test_idle_sweep_uses_synced_cost_when_evidence_empty():
    sub = str(uuid.uuid4())
    rid = "/subscriptions/aaa/resourcegroups/rg/providers/microsoft.compute/disks/d2"
    init_db()
    db = SessionLocal()
    try:
        db.query(OptimizationFinding).delete()
        db.query(CostByResourceSnapshot).delete()
        db.add(
            OptimizationFinding(
                id=str(uuid.uuid4()),
                run_id="run-1",
                rule_id="DISK_UNUSED_EXTENDED",
                rule_name="Extended Unused Disk Detection",
                category="COMPUTE",
                severity="HIGH",
                resource_id=rid,
                resource_name="d2",
                resource_type="compute/disk",
                subscription_id=sub,
                detail="Unattached",
                recommendation="Delete",
                estimated_savings_usd=0.0,
                evidence_json="{}",
                status="open",
            )
        )
        db.add(
            CostByResourceSnapshot(
                id=str(uuid.uuid4()),
                subscription_id=sub,
                resource_id=rid,
                service_name="Storage",
                month="2026-06",
                cost_usd=0.0,
                cost_billing=41.5,
                billing_currency="CAD",
            )
        )
        db.commit()
    finally:
        db.close()

    init_db()
    db = SessionLocal()
    try:
        db.query(AppUser).filter(AppUser.username == "admin").delete()
        db.add(
            AppUser(
                id="admin-idle-savings-cost",
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

    response = client.get(f"/api/idle-resources/sweep/{sub}")
    assert response.status_code == 200
    body = response.json()
    assert body["total_idle_findings"] == 1
    assert body["total_estimated_savings_usd"] == 41.5
    assert body["idle_resources"][0]["savings_source"] == "resource_cost"


def test_idle_sweep_uses_evidence_cost():
    sub = str(uuid.uuid4())
    init_db()
    db = SessionLocal()
    try:
        db.query(OptimizationFinding).delete()
        db.add(
            OptimizationFinding(
                id=str(uuid.uuid4()),
                run_id="run-1",
                rule_id="DISK_UNUSED_EXTENDED",
                rule_name="Extended Unused Disk Detection",
                category="COMPUTE",
                severity="HIGH",
                resource_id="/subscriptions/aaa/resourcegroups/rg/providers/microsoft.compute/disks/d1",
                resource_name="d1",
                resource_type="compute/disk",
                subscription_id=sub,
                detail="Unattached",
                recommendation="Delete",
                estimated_savings_usd=0.0,
                evidence_json=json.dumps({"monthly_cost_usd": 33.25}),
                status="open",
            )
        )
        db.commit()
    finally:
        db.close()

    init_db()
    db = SessionLocal()
    try:
        db.query(AppUser).filter(AppUser.username == "admin").delete()
        db.add(
            AppUser(
                id="admin-idle-savings",
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

    response = client.get(f"/api/idle-resources/sweep/{sub}")
    assert response.status_code == 200
    body = response.json()
    assert body["total_idle_findings"] == 1
    assert body["total_estimated_savings_usd"] == 33.25
    assert body["findings_with_savings"] == 1
    assert body["idle_resources"][0]["estimated_savings_usd"] == 33.25
    assert body["idle_resources"][0]["savings_source"] == "evidence_cost"
