"""Tests for Advisor VM target parsing and engine alignment."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.advisor_sync import normalize_advisor_item
from app.advisor_vm_targets import (
    AdvisorVmTarget,
    advisor_row_to_vm_target,
    load_advisor_vm_targets,
    parse_advisor_vm_skus,
)
from app.models import AdvisorRecommendation, Base
from app.optimizer.resource_engines.compute.vm.helpers import merge_advisor_vm_target
from app.vm_sizing import VmSizingRecommendation


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_parse_advisor_vm_skus_from_extended_properties():
    extended = {"currentSku": "Standard_D8s_v3", "targetSku": "Standard_D4s_v3"}
    current, target = parse_advisor_vm_skus(extended)
    assert current == "Standard_D8s_v3"
    assert target == "Standard_D4s_v3"


def test_normalize_advisor_item_extracts_vm_skus():
    item = {
        "name": "rec-vm",
        "properties": {
            "category": "Cost",
            "impact": "High",
            "recommendationTypeId": "39a8510b-812c-4530-ab2a-c8491f9bf666",
            "shortDescription": {"problem": "Resize VM"},
            "resourceMetadata": {
                "resourceId": "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
            },
            "extendedProperties": {
                "currentSku": "Standard_D8s_v3",
                "targetSku": "Standard_D4s_v3",
                "savingsAmount": "244.00",
            },
        },
    }
    row = normalize_advisor_item(item, "sub-1")
    assert row["current_sku"] == "Standard_D8s_v3"
    assert row["target_sku"] == "Standard_D4s_v3"
    assert row["recommendation_type_id"] == "39a8510b-812c-4530-ab2a-c8491f9bf666"


def test_merge_advisor_vm_target_overrides_engine_sku():
    sizing = VmSizingRecommendation(
        action="downgrade",
        current_sku="Standard_D8s_v3",
        suggested_sku="Standard_D2s_v3",
        current_family="D",
        suggested_family="D",
        family_label="General purpose",
        direction="down",
        avg_cpu_pct=5.0,
        avg_memory_pct=10.0,
        confidence=70,
        reasons=["Engine suggested smaller SKU."],
    )
    advisor = AdvisorVmTarget(
        resource_id="/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        recommendation_id="rec-1",
        current_sku="Standard_D8s_v3",
        target_sku="Standard_D4s_v3",
        recommendation_type_id="39a8510b-812c-4530-ab2a-c8491f9bf666",
        potential_savings_monthly=244.0,
        summary="Resize VM",
    )
    merged, meta = merge_advisor_vm_target(sizing, current_sku="Standard_D8s_v3", advisor=advisor)
    assert merged is not None
    assert merged.suggested_sku == "Standard_D4s_v3"
    assert meta["sku_source"] == "azure_advisor"


def test_load_advisor_vm_targets_from_db(db_session):
    rid = "/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1"
    db_session.add(AdvisorRecommendation(
        id=str(uuid.uuid4()),
        recommendation_id="rec-1",
        resource_id=rid,
        subscription_id="sub-1",
        category="Cost",
        impact="High",
        summary="Resize VM",
        potential_savings_monthly=244.0,
        recommendation_type_id="39a8510b-812c-4530-ab2a-c8491f9bf666",
        current_sku="Standard_D8s_v3",
        target_sku="Standard_D4s_v3",
        status="Active",
        generated_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    targets = load_advisor_vm_targets(db_session, "sub-1")
    assert rid.lower() in targets
    assert targets[rid.lower()].target_sku == "Standard_D4s_v3"


def test_advisor_row_to_vm_target_falls_back_to_raw_json():
    row = AdvisorRecommendation(
        id=str(uuid.uuid4()),
        recommendation_id="rec-2",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm2",
        subscription_id="sub-1",
        category="Cost",
        impact="High",
        summary="Resize VM",
        status="Active",
        generated_at=datetime.now(timezone.utc),
        raw_json={
            "properties": {
                "recommendationTypeId": "39a8510b-812c-4530-ab2a-c8491f9bf666",
                "extendedProperties": {
                    "currentSku": "Standard_E4s_v3",
                    "targetSku": "Standard_E2s_v3",
                },
            },
        },
    )
    target = advisor_row_to_vm_target(row)
    assert target is not None
    assert target.target_sku == "Standard_E2s_v3"
