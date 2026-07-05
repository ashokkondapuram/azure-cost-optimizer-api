"""Tests for generic ARM resource enrichment."""

from app.arm_resource_enrichment import (
    api_version_for_resource_id,
    enrich_arm_resources,
    needs_arm_enrichment,
)
from app.resources import get_technical_fetch_spec


class _FakeClient:
    def __init__(self, full_payload: dict):
        self.full_payload = full_payload
        self.get_calls = 0

    def get_arm_resource(self, resource_id: str, *, api_version=None):
        self.get_calls += 1
        return self.full_payload

    def get_application_gateway(self, subscription_id, resource_group, gateway_name):
        return self.get_arm_resource("")


def test_needs_enrichment_when_http_listeners_empty():
    spec = get_technical_fetch_spec("network/appgateway")
    thin = {"properties": {"provisioningState": "Succeeded"}}
    assert needs_arm_enrichment(thin, spec) is True
    full = {"properties": {"httpListeners": [{"name": "l1"}]}}
    assert needs_arm_enrichment(full, spec) is False


def test_needs_enrichment_when_backend_pools_empty():
    spec = get_technical_fetch_spec("network/loadbalancer")
    thin = {"properties": {"provisioningState": "Succeeded"}}
    assert needs_arm_enrichment(thin, spec) is True


def test_enrich_arm_resources_fetches_thin_list_rows():
    spec = get_technical_fetch_spec("network/appgateway")
    thin = {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/applicationGateways/agw1",
        "name": "agw1",
        "properties": {"provisioningState": "Succeeded"},
    }
    full = {
        **thin,
        "properties": {
            "provisioningState": "Succeeded",
            "httpListeners": [{"name": "https"}, {"name": "http"}],
        },
    }

    class _AgwClient:
        def __init__(self):
            self.get_application_gateway_calls = 0

        def get_application_gateway(self, subscription_id, resource_group, gateway_name, db=None):
            self.get_application_gateway_calls += 1
            return full

    client = _AgwClient()
    enriched = enrich_arm_resources(client, "sub", [thin], spec.canonical_type)
    assert client.get_application_gateway_calls == 1
    assert len(enriched[0]["properties"]["httpListeners"]) == 2


def test_enrich_skips_when_properties_complete():
    class _FailClient:
        def get_arm_resource(self, *args, **kwargs):
            raise AssertionError("should not GET")

    complete = {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/applicationGateways/agw1",
        "properties": {"httpListeners": [{"name": "only"}]},
    }
    enriched = enrich_arm_resources(_FailClient(), "sub", [complete], "network/appgateway")
    assert enriched[0]["properties"]["httpListeners"]


def test_enrich_disk_uses_get_disk():
    spec = get_technical_fetch_spec("compute/disk")
    thin = {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/disks/d1",
        "name": "d1",
        "properties": {"diskState": "Unattached", "diskSizeGB": 128},
    }
    full = {
        **thin,
        "properties": {
            **thin["properties"],
            "LastOwnershipUpdateTime": "2026-04-21T04:41:35.079872+00:00",
            "TimeCreated": "2026-04-20T04:41:35.079872+00:00",
        },
    }

    class _DiskClient:
        def __init__(self):
            self.get_disk_calls = 0

        def get_disk(self, subscription_id, resource_group, disk_name):
            self.get_disk_calls += 1
            return full

    client = _DiskClient()
    enriched = enrich_arm_resources(client, "sub", [thin], spec.canonical_type)
    assert client.get_disk_calls == 1
    assert enriched[0]["properties"]["LastOwnershipUpdateTime"]


def test_api_version_for_vmss_uses_compute_get_version():
    rid = (
        "/subscriptions/sub/resourceGroups/rg/providers/"
        "Microsoft.Compute/virtualMachineScaleSets/my-vmss"
    )
    assert api_version_for_resource_id(rid) == "2025-11-01"


def test_api_version_for_vm_uses_compute_get_version():
    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
    assert api_version_for_resource_id(rid) == "2025-11-01"


def test_enrich_vm_uses_get_vm():
    spec = get_technical_fetch_spec("compute/vm")
    thin = {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        "name": "vm1",
        "properties": {"provisioningState": "Succeeded"},
    }
    full = {
        **thin,
        "properties": {
            "provisioningState": "Succeeded",
            "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
            "instanceView": {"statuses": [{"code": "PowerState/running"}]},
        },
    }

    class _VmClient:
        def __init__(self):
            self.get_vm_calls = 0

        def get_vm(self, subscription_id, resource_group, vm_name, *, expand="instanceView"):
            self.get_vm_calls += 1
            assert expand == "instanceView"
            return full

    client = _VmClient()
    enriched = enrich_arm_resources(client, "sub", [thin], spec.canonical_type)
    assert client.get_vm_calls == 1
    assert enriched[0]["properties"]["hardwareProfile"]["vmSize"] == "Standard_D2s_v3"


def test_enrich_snapshot_uses_get_snapshot():
    spec = get_technical_fetch_spec("compute/snapshot")
    thin = {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/snapshots/snap1",
        "name": "snap1",
        "properties": {"provisioningState": "Succeeded"},
    }
    full = {
        **thin,
        "properties": {
            "provisioningState": "Succeeded",
            "diskSizeGB": 128,
            "timeCreated": "2026-04-20T04:41:35.079872+00:00",
            "diskState": "Unattached",
        },
    }

    class _SnapshotClient:
        def __init__(self):
            self.get_snapshot_calls = 0

        def get_snapshot(self, subscription_id, resource_group, snapshot_name):
            self.get_snapshot_calls += 1
            return full

    client = _SnapshotClient()
    enriched = enrich_arm_resources(client, "sub", [thin], spec.canonical_type)
    assert client.get_snapshot_calls == 1
    assert enriched[0]["properties"]["diskSizeGB"] == 128


def test_api_version_for_snapshot_uses_compute_get_version():
    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/snapshots/snap1"
    assert api_version_for_resource_id(rid) == "2026-03-02"


def test_api_version_for_appgateway_uses_application_gateway_get_version():
    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/applicationGateways/agw1"
    assert api_version_for_resource_id(rid) == "2025-05-01"


def test_enrich_storage_account_uses_get_storage_account():
    spec = get_technical_fetch_spec("storage/account")
    thin = {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/acct1",
        "name": "acct1",
        "kind": "StorageV2",
        "properties": {"provisioningState": "Succeeded"},
    }
    full = {
        **thin,
        "properties": {
            "provisioningState": "Succeeded",
            "accessTier": "Hot",
            "supportsHttpsTrafficOnly": True,
        },
    }

    class _StorageClient:
        def __init__(self):
            self.get_storage_account_calls = 0

        def get_storage_account(self, subscription_id, resource_group, account_name):
            self.get_storage_account_calls += 1
            return full

    client = _StorageClient()
    enriched = enrich_arm_resources(client, "sub", [thin], spec.canonical_type)
    assert client.get_storage_account_calls == 1
    assert enriched[0]["properties"]["accessTier"] == "Hot"


def test_needs_enrichment_skips_storage_when_kind_is_top_level():
    spec = get_technical_fetch_spec("storage/account")
    row = {
        "kind": "StorageV2",
        "properties": {"accessTier": "Hot", "provisioningState": "Succeeded"},
    }
    assert needs_arm_enrichment(row, spec) is False


def test_needs_enrichment_when_last_ownership_null_triggers_get():
    spec = get_technical_fetch_spec("compute/disk")
    thin = {
        "properties": {
            "diskSizeGB": 128,
            "diskState": "Unattached",
            "timeCreated": "2024-01-01T00:00:00Z",
            "lastOwnershipUpdateTime": None,
        },
    }
    assert needs_arm_enrichment(thin, spec) is True


def test_needs_enrichment_skips_disk_when_last_ownership_present():
    spec = get_technical_fetch_spec("compute/disk")
    full = {
        "properties": {
            "diskSizeGB": 128,
            "diskState": "Unattached",
            "timeCreated": "2024-01-01T00:00:00Z",
            "lastOwnershipUpdateTime": "2025-06-01T00:00:00Z",
        },
    }
    assert needs_arm_enrichment(full, spec) is False


def test_api_version_for_storage_account_uses_get_properties_version():
    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/acct1"
    assert api_version_for_resource_id(rid) == "2026-04-01"
