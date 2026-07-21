"""Tests for sidebar nav access policy and superuser role."""

import uuid

import pytest
from starlette.testclient import TestClient

from app.integration_app import app
from app.models import AppUser, Base
from app.database import SessionLocal, engine
from app.user_auth import ROLE_ADMIN, ROLE_SUPERUSER, ROLE_VIEWER, create_access_token, hash_password
from app.nav_access import (
    default_nav_access_policy,
    get_nav_access_policy,
    is_path_allowed,
    save_nav_access_policy,
)


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _auth_header(role: str, user_id: str = "u1", username: str = "tester") -> dict:
    token = create_access_token(user_id=user_id, username=username, role=role)
    return {"Authorization": f"Bearer {token}"}


def _seed_user(db, *, role: str, username: str) -> tuple[str, str]:
    user_id = str(uuid.uuid4())
    user = AppUser(
        id=user_id,
        username=username,
        display_name=username.title(),
        password_hash=hash_password("password123"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user_id, username


def test_superuser_sees_all_paths_by_default():
    policy = default_nav_access_policy()
    assert is_path_allowed("/settings", ROLE_SUPERUSER, policy)
    assert is_path_allowed("/costs", ROLE_VIEWER, policy)


def test_viewer_default_hides_admin_panels():
    policy = default_nav_access_policy()
    assert not is_path_allowed("/settings", ROLE_VIEWER, policy)
    assert is_path_allowed("/costs", ROLE_VIEWER, policy)


def test_save_policy_persists_overrides():
    db = SessionLocal()
    try:
        policy = default_nav_access_policy()
        policy[ROLE_VIEWER]["/costs"] = False
        save_nav_access_policy(db, policy)
        loaded = get_nav_access_policy(db)
        assert loaded[ROLE_VIEWER]["/costs"] is False
    finally:
        db.close()


def test_hiding_overview_section_blocks_dashboard():
    policy = default_nav_access_policy()
    policy[ROLE_VIEWER]["section:overview"] = False
    assert not is_path_allowed("/action-centre", ROLE_VIEWER, policy)
    assert not is_path_allowed("/dashboard", ROLE_VIEWER, policy)
    assert not is_path_allowed("/costs", ROLE_VIEWER, policy)


def test_action_centre_allowed_for_viewer_by_default():
    policy = default_nav_access_policy()
    assert is_path_allowed("/action-centre", ROLE_VIEWER, policy)
    assert not is_path_allowed("/explorer", ROLE_VIEWER, policy)
    assert not is_path_allowed("/explorer/issues", ROLE_VIEWER, policy)


def test_resource_inventory_superuser_only():
    policy = default_nav_access_policy()
    assert is_path_allowed("/explorer", ROLE_SUPERUSER, policy)
    assert not is_path_allowed("/explorer", ROLE_ADMIN, policy)
    assert not is_path_allowed("/explorer", ROLE_VIEWER, policy)
    policy[ROLE_ADMIN]["/explorer"] = True
    assert not is_path_allowed("/explorer", ROLE_ADMIN, policy)


def test_hiding_advanced_subgroup_blocks_only_that_subgroup():
    policy = default_nav_access_policy()
    policy[ROLE_VIEWER]["section:advanced:advanced-insights"] = False
    assert not is_path_allowed("/waste-heatmap", ROLE_VIEWER, policy)
    assert is_path_allowed("/budgets", ROLE_VIEWER, policy)


def test_hiding_resources_subgroup_blocks_compute_pages():
    policy = default_nav_access_policy()
    policy[ROLE_VIEWER]["section:resources:compute"] = False
    assert not is_path_allowed("/vms", ROLE_VIEWER, policy)
    assert is_path_allowed("/storage", ROLE_VIEWER, policy)


def test_hiding_entire_advanced_category_blocks_all_advanced_tools():
    policy = default_nav_access_policy()
    policy[ROLE_VIEWER]["section:advanced"] = False
    assert not is_path_allowed("/waste-heatmap", ROLE_VIEWER, policy)
    assert is_path_allowed("/costs", ROLE_VIEWER, policy)


def test_nav_access_policy_requires_superuser():
    client = TestClient(app)
    db = SessionLocal()
    try:
        admin_id, admin_name = _seed_user(db, role=ROLE_ADMIN, username="admin1")
        super_id, super_name = _seed_user(db, role=ROLE_SUPERUSER, username="super1")
    finally:
        db.close()

    assert client.get(
        "/settings/nav-access/policy",
        headers=_auth_header(ROLE_ADMIN, admin_id, admin_name),
    ).status_code == 403
    res = client.get(
        "/settings/nav-access/policy",
        headers=_auth_header(ROLE_SUPERUSER, super_id, super_name),
    )
    assert res.status_code == 200
    assert "catalog" in res.json()
    assert ROLE_VIEWER in res.json()["roles"]


def test_auth_me_includes_allowed_paths():
    client = TestClient(app)
    db = SessionLocal()
    try:
        viewer_id, viewer_name = _seed_user(db, role=ROLE_VIEWER, username="viewer1")
    finally:
        db.close()

    res = client.get("/auth/me", headers=_auth_header(ROLE_VIEWER, viewer_id, viewer_name))
    assert res.status_code == 200
    body = res.json()
    assert body["role"] == ROLE_VIEWER
    assert "/costs" in body["allowed_paths"]
    assert "/action-centre" in body["allowed_paths"]
    assert "/settings" not in body["allowed_paths"]
