"""VMSS is embedded under AKS only — not standalone inventory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.db_sync import _deactivate_standalone_vmss_rows
from app.inventory_standalone import (
    STANDALONE_INVENTORY_EXCLUDED,
    filter_standalone_inventory_rows,
    is_standalone_inventory_type,
)
from app.resource_store import get_resources_db
from app.sync_scope import canonical_type_from_api_path, inventory_syncable_types, types_for_api_path


def test_compute_vmss_is_excluded_from_standalone_inventory():
    assert "compute/vmss" in STANDALONE_INVENTORY_EXCLUDED
    assert not is_standalone_inventory_type("compute/vmss")
    assert is_standalone_inventory_type("compute/vm")


def test_filter_standalone_inventory_rows_drops_vmss():
    rows = [
        {"id": "/a", "type": "compute/vm", "name": "vm1"},
        {"id": "/b", "type": "compute/vmss", "name": "aks-system-vmss"},
        {
            "id": (
                "/subscriptions/s/resourceGroups/MC_rg/providers/"
                "Microsoft.Compute/virtualMachineScaleSets/aks-nodepool"
            ),
            "type": "compute/vm",
            "name": "mislabeled-vmss",
        },
        {"id": "/c", "type": "containers/aks", "name": "prod-aks"},
    ]
    filtered = filter_standalone_inventory_rows(rows)
    assert [row["type"] for row in filtered] == ["compute/vm", "containers/aks"]
    assert filtered[0]["name"] == "vm1"


def test_vmss_not_in_inventory_syncable_types():
    assert "compute/vmss" not in inventory_syncable_types()


def test_vmss_api_path_not_mapped_for_sync():
    assert canonical_type_from_api_path("/resources/vmss") is None
    assert types_for_api_path("/resources/vmss") == []


def test_get_resources_db_returns_empty_for_vmss_without_query():
    db = MagicMock()
    rows = get_resources_db(db, "sub-a", "compute/vmss", include_properties=True)
    assert rows == []
    db.query.assert_not_called()


def test_deactivate_standalone_vmss_rows_marks_snapshots_inactive():
    from app.models import ResourceSnapshot

    row = MagicMock(spec=ResourceSnapshot)
    row.resource_id = (
        "/subscriptions/sub-a/resourceGroups/MC_rg/providers/"
        "Microsoft.Compute/virtualMachineScaleSets/aks-system-vmss"
    )
    row.is_active = True

    db = MagicMock()
    db.query.return_value.filter.return_value.yield_per.return_value = [row]

    with patch("app.db_sync._resolve_findings_for_missing_resources", return_value=0):
        with patch("app.data_store.enrichment_registry.get_enrichment_model") as get_model:
            model = MagicMock()
            get_model.return_value = model
            model_query = model
            db.query.return_value.filter.return_value.delete.return_value = 0
            removed = _deactivate_standalone_vmss_rows(db, "sub-a")

    assert removed == 1
    assert row.is_active is False


def test_aks_cluster_still_lists_with_embedded_vmss():
    import json

    props = {
        "kubernetesVersion": "1.29.0",
        "nodeResourceGroup": "MC_rg",
        "agentPoolProfiles": [
            {
                "name": "system",
                "count": 3,
                "vmSize": "Standard_D4s_v5",
                "virtualMachineScaleSet": {
                    "id": (
                        "/subscriptions/sub-a/resourceGroups/MC_rg/providers/"
                        "Microsoft.Compute/virtualMachineScaleSets/aks-system-vmss"
                    ),
                    "name": "aks-system-vmss",
                },
            }
        ],
    }
    snap = MagicMock()
    snap.resource_id = (
        "/subscriptions/sub-a/resourceGroups/rg/providers/"
        "Microsoft.ContainerService/managedClusters/prod-aks"
    )
    snap.resource_name = "prod-aks"
    snap.resource_type = "containers/aks"
    snap.resource_group = "rg"
    snap.location = "eastus"
    snap.state = None
    snap.sku = None
    snap.sku_json = "{}"
    snap.tags_json = "{}"
    snap.analysis_summary_json = "[]"
    snap.properties_json = json.dumps(props)
    snap.synced_at = None
    snap.is_cost_export_only = False

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [snap]

    with patch("app.resource_store._cost_map_for_subscription", return_value={}):
        with patch("app.resource_store._apply_resource_costs", side_effect=lambda rows, *a, **k: rows):
            with patch("app.resource_enrichment.overlay_list_rows_from_enrichment", side_effect=lambda _db, _sub, rows: rows):
                rows = get_resources_db(db, "sub-a", "containers/aks", include_properties=True)

    assert len(rows) == 1
    pools = rows[0]["properties"]["agentPoolProfiles"]
    assert pools[0]["virtualMachineScaleSet"]["name"] == "aks-system-vmss"
