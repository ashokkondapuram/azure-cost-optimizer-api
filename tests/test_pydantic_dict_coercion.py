"""Tests for API request coercion of null or malformed dict fields."""

from app.routers.k8s import K8sSnapshotIn
from app.routers.optimize import (
    AnalyzeRequest,
    BatchResourceLookupIn,
    FindingExecutionIn,
    ProfileValidateIn,
)
from app.routers.resources_inventory import _vm_sizing_timespan
from app.validators import (
    coerce_bool_dict_map,
    coerce_dict,
    coerce_nested_dict_map,
    coerce_str_dict,
)


def test_coerce_dict_handles_null_and_json_string():
    assert coerce_dict(None) == {}
    assert coerce_dict([]) == {}
    assert coerce_dict('{"enabled": true}') == {"enabled": True}
    assert coerce_dict("[object Object]") == {}


def test_coerce_nested_dict_map_drops_invalid_inner_values():
    assert coerce_nested_dict_map(None) == {}
    assert coerce_nested_dict_map({"VM_IDLE": None}) == {}
    assert coerce_nested_dict_map({"VM_IDLE": {"cpu_idle_pct": 5}}) == {
        "VM_IDLE": {"cpu_idle_pct": 5},
    }


def test_coerce_str_dict_normalizes_tag_maps():
    assert coerce_str_dict(None) == {}
    assert coerce_str_dict({"env": "prod", "owner": None}) == {"env": "prod"}


def test_coerce_bool_dict_map_normalizes_nav_access_payload():
    assert coerce_bool_dict_map(None) == {}
    assert coerce_bool_dict_map({"admin": None}) == {}
    assert coerce_bool_dict_map({"admin": {"costs": True, "disks": False}}) == {
        "admin": {"costs": True, "disks": False},
    }


def test_batch_resource_lookup_accepts_null_timespan():
    payload = BatchResourceLookupIn(
        subscription_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        resource_ids=["/subscriptions/a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"],
        timespan=None,
    )
    assert payload.timespan == "P7D"


def test_analyze_request_accepts_null_rule_overrides():
    payload = AnalyzeRequest(
        subscription_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        rule_overrides=None,
        timespan_metrics={"value": "P14D", "label": "Last 14 days"},
    )
    assert payload.rule_overrides == {}
    assert payload.timespan_metrics == "P14D"


def test_profile_validate_accepts_null_draft_overrides():
    payload = ProfileValidateIn(draft_overrides=None)
    assert payload.draft_overrides == {}


def test_finding_execution_accepts_null_before_state():
    payload = FindingExecutionIn(action_type="manual_apply", before_state=None)
    assert payload.before_state == {}


def test_k8s_snapshot_accepts_null_summary_and_nodes():
    payload = K8sSnapshotIn(cluster_name="aks-demo", summary=None, nodes=None, pods=None)
    assert payload.summary == {}
    assert payload.nodes == []
    assert payload.pods == []


def test_vm_sizing_timespan_coerces_object_query_value():
    assert _vm_sizing_timespan({"value": "P30D", "label": "Last 30 days"}) == "P30D"


def test_finding_execution_coerces_non_dict_before_state_to_empty_dict():
    payload = FindingExecutionIn(action_type="manual_apply", before_state="not-a-dict")
    assert payload.before_state == {}
