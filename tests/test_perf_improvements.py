"""Tests for backend performance improvements."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.http_cache import cache_policy_for_path
from app.models import Base, OptimizationFinding, ResourceSnapshot
from app.resource_store import get_resources_db_page, rows_to_list


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_rows_to_list_omits_properties_when_disabled():
    row = ResourceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id="sub-1",
        resource_id="/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        resource_name="vm1",
        resource_type="compute/vm",
        resource_group="rg",
        location="eastus",
        sku="Standard_D2s_v3",
        state="running",
        properties_json='{"powerState": "running", "big": "' + ("x" * 1000) + '"}',
        tags_json='{"env": "dev"}',
        is_active=True,
        is_cost_export_only=False,
    )
    items = rows_to_list([row], include_properties=False)
    assert "properties" not in items[0]
    assert "tags" not in items[0]
    assert items[0]["name"] == "vm1"


def test_get_resources_db_page_excludes_cost_export_rows(db_session):
    db_session.add(ResourceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id="sub-1",
        resource_id="/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/real",
        resource_name="real-vm",
        resource_type="compute/vm",
        is_active=True,
        is_cost_export_only=False,
    ))
    db_session.add(ResourceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id="sub-1",
        resource_id="/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/export",
        resource_name="export-vm",
        resource_type="compute/vm",
        is_active=True,
        is_cost_export_only=True,
    ))
    db_session.commit()

    page = get_resources_db_page(db_session, "sub-1", "compute/vm", limit=50)
    names = {item["name"] for item in page["items"]}
    assert names == {"real-vm"}


def test_finding_status_query_uses_index_friendly_filter(db_session):
    finding = OptimizationFinding(
        id=str(uuid.uuid4()),
        run_id="run-1",
        rule_id="VM_UNDERUTILIZED_EXTENDED",
        rule_name="Underutilized VM",
        category="COMPUTE",
        severity="HIGH",
        resource_id="/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        resource_name="vm1",
        resource_type="compute/vm",
        subscription_id="sub-1",
        detail="detail",
        recommendation="rec",
        estimated_savings_usd=10.0,
        status="open",
        detected_at=datetime.now(timezone.utc),
    )
    db_session.add(finding)
    db_session.commit()

    hit = (
        db_session.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == "sub-1",
            OptimizationFinding.status == "open",
        )
        .all()
    )
    assert len(hit) == 1


def test_cache_policy_for_resource_lists():
    assert "max-age=300" in cache_policy_for_path("/resources/vms")
    assert cache_policy_for_path("/optimize/jobs/abc") == "no-store"
    assert "max-age=120" in cache_policy_for_path("/optimize/findings")


def test_perf_cache_metrics_track_hits_and_misses():
    from app.perf_cache import cached_cost_map, clear_subscription_read_caches, perf_cache_metrics

    clear_subscription_read_caches()
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        return {"a": 1}

    cached_cost_map("metrics-test", loader)
    cached_cost_map("metrics-test", loader)
    metrics = perf_cache_metrics()
    assert calls["n"] == 1
    assert metrics["hits"] >= 1
    assert metrics["misses"] >= 1
