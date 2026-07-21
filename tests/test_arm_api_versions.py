"""Tests for centralized ARM API version registry."""

from app.arm_api_versions import ARM_GET_API_VERSIONS, api_version_for_arm_type
from app.arm_resource_enrichment import api_version_for_resource_id


def test_vm_and_vmss_share_compute_api_version():
    assert ARM_GET_API_VERSIONS["microsoft.compute/virtualmachines"] == "2025-11-01"
    assert ARM_GET_API_VERSIONS["microsoft.compute/virtualmachinescalesets"] == "2025-11-01"


def test_api_version_for_vmss_resource_id():
    rid = (
        "/subscriptions/sub/resourceGroups/rg/providers/"
        "Microsoft.Compute/virtualMachineScaleSets/my-vmss"
    )
    assert api_version_for_resource_id(rid) == "2025-11-01"


def test_network_resources_use_2024_05_01():
    assert api_version_for_arm_type("microsoft.network/loadbalancers") == "2024-05-01"
    assert api_version_for_arm_type("microsoft.network/publicipaddresses") == "2024-05-01"
    assert api_version_for_arm_type("microsoft.network/privatednszones") == "2024-06-01"


def test_all_registered_arm_types_have_versions():
    assert len(ARM_GET_API_VERSIONS) >= 30
    for arm_type, version in ARM_GET_API_VERSIONS.items():
        assert "/" in arm_type
        assert version
