"""Tests for Azure-backed resource health classification."""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, ResourceSnapshot
from app.resource_health import (
    aggregate_health_counts,
    classify_resource_from_snapshot,
    classify_resource_health,
    get_subscription_health_counts,
    map_azure_availability_state,
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _add_resource(
    db,
    *,
    rid: str,
    rtype: str = "compute/vm",
    state: str | None = None,
    properties: dict | None = None,
):
    db.add(ResourceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id="sub-1",
        resource_id=rid.lower(),
        resource_name=rid.split("/")[-1],
        resource_type=rtype,
        resource_group="rg-1",
        location="eastus",
        state=state,
        properties_json=json.dumps(properties or {}),
        synced_at=datetime.now(timezone.utc),
    ))


def test_map_azure_availability_state():
    assert map_azure_availability_state("Available") == "healthy"
    assert map_azure_availability_state("Degraded") == "degraded"
    assert map_azure_availability_state("Unavailable") == "unavailable"
    assert map_azure_availability_state("Unknown") == "unknown"


def test_classify_resource_from_snapshot_provisioning_failed():
    category = classify_resource_from_snapshot(
        state="Succeeded",
        properties={"provisioningState": "Failed"},
        resource_type="compute/vm",
    )
    assert category == "unavailable"


def test_classify_resource_from_snapshot_running_vm_is_healthy():
    category = classify_resource_from_snapshot(
        state="PowerState/running",
        properties={"provisioningState": "Succeeded", "powerState": "PowerState/running"},
        resource_type="compute/vm",
    )
    assert category == "healthy"


def test_classify_resource_health_prefers_azure_signal():
    category = classify_resource_health(
        state="PowerState/running",
        properties={"provisioningState": "Succeeded"},
        resource_type="compute/vm",
        azure_availability_state="Unavailable",
    )
    assert category == "unavailable"


def test_aggregate_health_counts_mixed_sources():
    resources = [
        (
            "/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm-1",
            "compute/vm",
            "PowerState/running",
            {"provisioningState": "Succeeded"},
        ),
        (
            "/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.cache/redis/cache-1",
            "database/redis",
            "Failed",
            {"provisioningState": "Failed"},
        ),
    ]
    azure_map = {
        resources[0][0]: "Degraded",
    }
    result = aggregate_health_counts(resources, azure_map)
    assert result["healthy"] == 0
    assert result["degraded"] == 1
    assert result["unavailable"] == 1
    assert result["unknown"] == 0
    assert result["total"] == 2
    assert result["source"] == "mixed"


def test_get_subscription_health_counts_uses_inventory_when_azure_unavailable(db_session):
    rid = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1"
    _add_resource(
        db_session,
        rid=rid,
        properties={"provisioningState": "Succeeded", "powerState": "PowerState/running"},
    )
    db_session.commit()

    with patch("app.resource_health._load_azure_availability_map", return_value={}):
        result = get_subscription_health_counts(db_session, "sub-1")

    assert result["healthy"] == 1
    assert result["degraded"] == 0
    assert result["unavailable"] == 0
    assert result["source"] == "inventory_properties"


def test_get_subscription_health_counts_uses_cached_azure_statuses(db_session):
    rid = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1"
    _add_resource(db_session, rid=rid, properties={"provisioningState": "Succeeded"})
    db_session.commit()

    azure_map = {rid.lower(): "Unavailable"}
    with patch("app.resource_health._load_azure_availability_map", return_value=azure_map):
        result = get_subscription_health_counts(db_session, "sub-1")

    assert result["unavailable"] == 1
    assert result["healthy"] == 0
    assert result["source"] == "azure_resource_health"


def test_load_azure_availability_map_skips_when_disabled(db_session, monkeypatch):
    monkeypatch.setattr("app.resource_health._azure_health_enabled", lambda: False)

    from app.resource_health import _load_azure_availability_map

    with patch("app.auth.cached_arm_token_available") as token_check:
        assert _load_azure_availability_map(db_session, "sub-1") == {}
        token_check.assert_not_called()


def test_load_azure_availability_map_times_out(db_session, monkeypatch):
    import time

    from app.resource_health import _load_azure_availability_map

    monkeypatch.setattr("app.resource_health._azure_health_enabled", lambda: True)
    monkeypatch.setattr("app.auth.cached_arm_token_available", lambda db: True)
    monkeypatch.setattr("app.resource_health._azure_health_timeout_sec", lambda: 0.2)
    monkeypatch.setattr(
        "app.resource_health.cached_azure_health_statuses",
        lambda sub, loader: loader(),
    )

    class _SlowClient:
        def list_availability_statuses(self, subscription_id):
            time.sleep(1.0)
            return [{
                "id": "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1",
                "properties": {"availabilityState": "Available"},
            }]

    monkeypatch.setattr(
        "app.azure_maintenance.AzureMaintenanceClient",
        lambda db=None: _SlowClient(),
    )

    started = time.monotonic()
    result = _load_azure_availability_map(db_session, "sub-1")
    elapsed = time.monotonic() - started

    assert result == {}
    assert elapsed < 1.0
