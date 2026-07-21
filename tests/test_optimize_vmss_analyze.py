"""VMSS in MC_* resource groups must analyze through parent AKS cluster."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.analysis.orchestrator import run_resource_db_analysis
from app.focus_mapping import normalize_arm_id
from app.inventory_standalone import (
    EMBEDDED_VMSS_ANALYSIS_MESSAGE,
    resolve_aks_cluster_for_embedded_vmss,
)
from app.models import Base, ResourceSnapshot

SUB = "93ca908b-5732-440d-b712-f6d7951951c0"
VMSS_ID = (
    f"/subscriptions/{SUB}/resourceGroups/"
    "mc_agrdevv2rg2cc_agrdevv2rg2cc_canadacentral/providers/"
    "Microsoft.Compute/virtualMachineScaleSets/aks-zioapp2-30260430-vmss"
)
AKS_ID = (
    f"/subscriptions/{SUB}/resourceGroups/agrdevv2rg2cc/providers/"
    "Microsoft.ContainerService/managedClusters/zioapp2"
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _add_aks_snapshot(db, *, vmss_id: str = VMSS_ID, pool_name: str = "zioapp2"):
    props = {
        "kubernetesVersion": "1.29.0",
        "nodeResourceGroup": "mc_agrdevv2rg2cc_agrdevv2rg2cc_canadacentral",
        "agentPoolProfiles": [
            {
                "name": pool_name,
                "count": 3,
                "vmSize": "Standard_D4s_v5",
                "virtualMachineScaleSet": {
                    "id": vmss_id,
                    "name": vmss_id.rsplit("/", 1)[-1],
                },
            }
        ],
    }
    db.add(
        ResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=SUB,
            resource_id=normalize_arm_id(AKS_ID),
            resource_name="zioapp2",
            resource_type="containers/aks",
            resource_group="agrdevv2rg2cc",
            location="canadacentral",
            state="running",
            properties_json=json.dumps(props),
            tags_json="{}",
            sku_json="{}",
            is_active=True,
            synced_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


def test_resolve_aks_cluster_for_embedded_vmss_matches_pool_ref(db):
    _add_aks_snapshot(db)
    parent = resolve_aks_cluster_for_embedded_vmss(db, SUB, VMSS_ID)
    assert parent == normalize_arm_id(AKS_ID)


def test_resolve_aks_cluster_for_embedded_vmss_returns_none_without_cluster(db):
    assert resolve_aks_cluster_for_embedded_vmss(db, SUB, VMSS_ID) is None


@patch("app.analysis.orchestrator.run_db_analysis")
def test_run_resource_db_analysis_redirects_vmss_to_parent_aks(mock_run, db):
    _add_aks_snapshot(db)
    mock_run.return_value = {"summary": {"total_findings": 0}}

    run_resource_db_analysis(
        db,
        subscription_id=SUB,
        resource_id=VMSS_ID,
    )

    mock_run.assert_called_once()
    kwargs = mock_run.call_args.kwargs
    assert kwargs["scope_resource_types"] == ["containers/aks"]
    assert kwargs["scope_resource_ids"] == [normalize_arm_id(AKS_ID)]


def test_run_resource_db_analysis_rejects_orphan_vmss(db):
    with pytest.raises(ValueError, match=EMBEDDED_VMSS_ANALYSIS_MESSAGE):
        run_resource_db_analysis(
            db,
            subscription_id=SUB,
            resource_id=VMSS_ID,
        )
