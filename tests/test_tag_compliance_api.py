"""Tests for tag compliance API."""

import json
import uuid

from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.main import app
from app.models import AppUser, ResourceSnapshot
from app.user_auth import ROLE_ADMIN, hash_password

SUBSCRIPTION_ID = str(uuid.uuid4())


def _auth_client() -> TestClient:
    init_db()
    db = SessionLocal()
    try:
        db.query(AppUser).filter(AppUser.username == "admin").delete()
        db.commit()
        db.add(
            AppUser(
                id="admin-tag-compliance",
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


def _seed_resources(rows: list[ResourceSnapshot]) -> None:
    init_db()
    db = SessionLocal()
    try:
        db.query(ResourceSnapshot).filter(ResourceSnapshot.subscription_id == SUBSCRIPTION_ID).delete()
        for row in rows:
            db.add(row)
        db.commit()
    finally:
        db.close()


def test_tag_compliance_reads_tags_json_and_returns_aggregates():
    _seed_resources([
        ResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=SUBSCRIPTION_ID,
            resource_id="/subscriptions/a/resourcegroups/rg1/providers/microsoft.compute/virtualmachines/vm1",
            resource_name="vm1",
            resource_type="compute/vm",
            resource_group="rg1",
            tags_json=json.dumps({"Environment": "prod", "Owner": "team-a", "cost-center": "cc1"}),
            is_active=True,
            is_cost_export_only=False,
        ),
        ResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=SUBSCRIPTION_ID,
            resource_id="/subscriptions/a/resourcegroups/rg1/providers/microsoft.compute/disks/d1",
            resource_name="d1",
            resource_type="compute/disk",
            resource_group="rg1",
            tags_json=json.dumps({"environment": "prod"}),
            is_active=True,
            is_cost_export_only=False,
        ),
    ])

    client = _auth_client()
    response = client.get(
        f"/api/tag-compliance/score/{SUBSCRIPTION_ID}",
        params={"required_tags": ["environment", "owner", "cost-center"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_resources"] == 2
    assert body["fully_compliant"] == 1
    assert body["non_compliant_count"] == 1
    assert body["score_pct"] == 50.0
    assert body["tag_missing_counts"]["owner"] == 1
    assert body["non_compliant_resources"][0]["resource_name"] == "d1"
    assert body["groups"][0]["resource_group"] == "rg1"
    assert body["by_resource_type"]
