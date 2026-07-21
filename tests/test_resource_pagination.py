"""Tests for paginated resource DB reads."""

import json
import uuid

from app.database import SessionLocal, init_db
from app.resource_store import get_resources_db_page, DEFAULT_RESOURCE_PAGE_SIZE
from app.models import ResourceSnapshot


def _seed_row(db, sub: str, name: str, rtype: str = "compute/vm", properties: dict | None = None):
    row = ResourceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id=sub,
        resource_id=f"/subscriptions/{sub}/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/{name}",
        resource_name=name,
        resource_type=rtype,
        resource_group="rg",
        is_active=True,
        properties_json=json.dumps(properties or {}),
        tags_json="{}",
    )
    db.add(row)
    db.commit()


def _seed_aks_row(db, sub: str, name: str, *, k8s_version: str, network_plugin: str):
    props = {
        "kubernetesVersion": k8s_version,
        "networkProfile": {"networkPlugin": network_plugin, "networkPolicy": "calico"},
        "agentPoolProfiles": [{"name": "nodepool1", "count": 2, "vmSize": "Standard_D2s_v3"}],
        "powerState": {"code": "PowerState/running"},
    }
    row = ResourceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id=sub,
        resource_id=(
            f"/subscriptions/{sub}/resourceGroups/rg/providers/"
            f"Microsoft.ContainerService/managedClusters/{name}"
        ),
        resource_name=name,
        resource_type="containers/aks",
        resource_group="rg",
        is_active=True,
        properties_json=json.dumps(props),
        tags_json="{}",
    )
    db.add(row)
    db.commit()


def test_get_resources_db_page():
    init_db()
    db = SessionLocal()
    try:
        sub = str(uuid.uuid4())
        for i in range(5):
            _seed_row(db, sub, f"vm-{i}")

        page = get_resources_db_page(db, sub, "compute/vm", limit=2, offset=0)
        assert page["total"] == 5
        assert len(page["items"]) == 2
        assert page["has_more"] is True
    finally:
        db.close()


def test_get_resources_db_page_advances_when_vmss_rows_filtered():
    """Pagination must advance by DB row count even when post-filter items are empty."""
    init_db()
    db = SessionLocal()
    try:
        sub = str(uuid.uuid4())
        _seed_row(
            db,
            sub,
            "aaa-vmss-instance",
            properties={"virtualMachineScaleSet": {"id": "/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/vmss1"}},
        )
        _seed_row(db, sub, "standalone-vm")

        page = get_resources_db_page(
            db, sub, "compute/vm", limit=1, offset=0, include_properties=True,
        )
        assert page["page_count"] == 1
        assert page["has_more"] is True
        assert page["items"] == []

        page2 = get_resources_db_page(
            db, sub, "compute/vm", limit=1, offset=1, include_properties=True,
        )
        assert len(page2["items"]) == 1
        assert page2["items"][0]["name"] == "standalone-vm"
    finally:
        db.close()


def test_default_page_size():
    assert DEFAULT_RESOURCE_PAGE_SIZE == 50


def test_get_resources_db_page_cursor_keyset():
    """Keyset cursor pagination returns next_cursor and stable pages."""
    init_db()
    db = SessionLocal()
    try:
        sub = str(uuid.uuid4())
        for i in range(5):
            _seed_row(db, sub, f"vm-{i}")

        page1 = get_resources_db_page(db, sub, "compute/vm", limit=2, offset=0)
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True
        assert page1.get("next_cursor")

        page2 = get_resources_db_page(
            db, sub, "compute/vm", limit=2, offset=2, cursor=page1["next_cursor"],
        )
        assert len(page2["items"]) == 2
        names1 = {i["name"] for i in page1["items"]}
        names2 = {i["name"] for i in page2["items"]}
        assert names1.isdisjoint(names2)
    finally:
        db.close()


def test_aks_page_includes_kubernetes_and_network_when_properties_requested():
    init_db()
    db = SessionLocal()
    try:
        sub = str(uuid.uuid4())
        _seed_aks_row(db, sub, "aks-prod", k8s_version="1.29.7", network_plugin="azure")

        without = get_resources_db_page(
            db, sub, "containers/aks", limit=10, offset=0, include_properties=False,
        )
        assert "properties" not in without["items"][0]

        with_props = get_resources_db_page(
            db, sub, "containers/aks", limit=10, offset=0, include_properties=True,
        )
        props = with_props["items"][0]["properties"]
        assert props["kubernetesVersion"] == "1.29.7"
        assert props["networkProfile"]["networkPlugin"] == "azure"
    finally:
        db.close()
