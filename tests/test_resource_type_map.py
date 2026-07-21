"""Tests for ARM / cost-export resource type mapping."""

from app.resource_type_map import (
    arm_provider_type,
    internal_resource_type,
    resource_name_from_arm_id,
)
from app.focus_mapping import normalize_arm_id


def test_arm_provider_type_from_resource_id():
    rid = (
        "/subscriptions/abc/resourcegroups/rg-prod/providers/"
        "Microsoft.Compute/virtualMachines/vm-web-01"
    )
    assert arm_provider_type(rid) == "microsoft.compute/virtualmachines"


def test_internal_resource_type_vm():
    rid = (
        "/subscriptions/abc/resourcegroups/rg/providers/"
        "Microsoft.Compute/virtualMachines/myvm"
    )
    assert internal_resource_type(rid, "Microsoft.Compute/virtualMachines") == "compute/vm"


def test_internal_resource_type_log_analytics():
    rid = (
        "/subscriptions/abc/resourcegroups/rg/providers/"
        "Microsoft.OperationalInsights/workspaces/log-analytics"
    )
    assert internal_resource_type(rid) == "monitoring/loganalytics"


def test_internal_resource_type_unknown_maps_to_other():
    rid = (
        "/subscriptions/abc/resourcegroups/rg/providers/"
        "Microsoft.CustomProvider/widgets/widget-01"
    )
    assert internal_resource_type(rid).startswith("other/")


def test_resource_name_from_arm_id():
    rid = "/subscriptions/x/resourcegroups/rg/providers/microsoft.compute/disks/disk1"
    assert resource_name_from_arm_id(rid) == "disk1"


def test_normalize_arm_id_strips_trailing_slash():
    raw = "/subscriptions/x/resourcegroups/rg/providers/microsoft.compute/disks/d1/"
    assert normalize_arm_id(raw) == (
        "/subscriptions/x/resourcegroups/rg/providers/microsoft.compute/disks/d1"
    )
