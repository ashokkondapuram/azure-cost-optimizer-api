"""Tests for subscription-wide ARM resource discovery sync."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.resource_type_map import inventory_canonical_for_arm_type
from app.sync_scope import inventory_syncable_types


def test_inventory_canonical_exact_match_only():
    assert inventory_canonical_for_arm_type("Microsoft.Network/privateEndpoints") == "network/privateendpoint"
    assert inventory_canonical_for_arm_type("microsoft.compute/virtualmachines") == "compute/vm"
    # Child types must not inherit parent mapping
    assert inventory_canonical_for_arm_type("microsoft.compute/virtualmachines/extensions") is None
    assert inventory_canonical_for_arm_type("microsoft.network/privatednszones/virtualnetworklinks") is None
    assert inventory_canonical_for_arm_type("microsoft.managedidentity/userassignedidentities") is None


def test_inventory_syncable_types_include_private_link():
    syncable = inventory_syncable_types()
    assert "network/privateendpoint" in syncable
    assert "network/privatelinkservice" in syncable
    assert "network/privatedns" in syncable
    assert "compute/batch" not in syncable


def test_sync_resource_discovery_groups_and_upserts():
    from app.resource_discovery_sync import sync_resource_discovery

    pe = {
        "id": "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Network/privateEndpoints/pe1",
        "name": "pe1",
        "type": "Microsoft.Network/privateEndpoints",
        "location": "eastus",
        "properties": {"provisioningState": "Succeeded"},
    }
    unknown = {
        "id": "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id1",
        "name": "id1",
        "type": "Microsoft.ManagedIdentity/userAssignedIdentities",
        "location": "eastus",
        "properties": {},
    }
    client = MagicMock()
    client.list_resources.return_value = [pe, unknown]

    db = MagicMock()
    token = "token"

    with patch("app.resource_discovery_sync.AzureResourcesClient", return_value=client):
        with patch("app.resource_discovery_sync.arm_auth_context"):
            with patch("app.resource_discovery_sync.arm_patient_sync"):
                with patch("app.resource_discovery_sync.VmSkuCatalogCache"):
                    with patch("app.resource_discovery_sync.enrich_arm_resources_for_type", side_effect=lambda _c, _s, items, _t: items):
                        with patch("app.resource_discovery_sync._upsert_arm_resource") as upsert:
                            with patch("app.resource_discovery_sync._prune_stale_resources", return_value={}):
                                with patch("app.resource_discovery_sync.audit_from_arm_items") as audit_mock:
                                    audit_mock.return_value = {
                                        "gaps": [],
                                        "free_skipped_unmapped_count": 1,
                                        "free_skipped_unmapped_types": {
                                            "microsoft.managedidentity/userassignedidentities": 1,
                                        },
                                    }
                                    result = sync_resource_discovery("sub-a", db, token)

    assert result["total_listed"] == 2
    assert result["resource_counts"]["network/privateendpoint"] == 1
    assert result["unmapped_count"] == 0
    assert result["free_skipped_unmapped_count"] == 1
    upsert.assert_called_once()
    db.commit.assert_called_once()
