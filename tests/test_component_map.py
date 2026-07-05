"""Tests for optimization component ↔ resource type mapping."""

from app.optimizer.component_map import (
    resolve_batches,
    resource_types_for_components,
    sync_types_for_component,
)


def test_sync_types_for_managed_disks():
    types = sync_types_for_component("Managed Disks")
    assert types == ["compute/disk"]


def test_sync_types_for_disk_snapshots():
    types = sync_types_for_component("Disk Snapshots")
    assert types == ["compute/snapshot"]


def test_resolve_batches_scoped():
    batches = resolve_batches(["Virtual Machines"])
    assert len(batches) == 1
    assert batches[0]["component"] == "Virtual Machines"


def test_resource_types_for_components():
    types = resource_types_for_components(["AKS", "Virtual Machines"])
    assert types == {"containers/aks", "compute/vm"}
