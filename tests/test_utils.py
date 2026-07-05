"""Tests for shared app utilities."""

import json

from app.utils import json_field, norm_arm_id, parse_tags_json


def test_json_field_serializes_dict_and_list():
    assert json_field({"a": 1}) == json.dumps({"a": 1})
    assert json_field([1, 2]) == json.dumps([1, 2])
    assert json_field('{"x": 1}') == '{"x": 1}'
    assert json_field(None, default="[]") == "[]"


def test_norm_arm_id_lowercases_and_trims():
    rid = "/subscriptions/ABC/resourceGroups/RG/providers/Microsoft.Compute/virtualMachines/VM"
    assert norm_arm_id(f"  {rid}  ") == rid.lower()


def test_parse_tags_json_normalizes_keys_and_values():
    assert parse_tags_json('{"Owner": "TeamA"}') == {"owner": "teama"}
    assert parse_tags_json({"Critical": "Yes"}) == {"critical": "yes"}
