"""Tests for unified rule registry and cost-export config overrides."""

import copy

from app.cost_export_recommendations import (
    COST_EXPORT_RULES_BY_ID,
    analyze_cost_export_resources,
    effective_cost_export_rules,
)
from app.optimizer.engine import OptimizationEngine, Finding
from app.optimizer.rule_catalog import list_all_rules, serialize_cost_export_rule
from app.optimizer.rule_overrides import apply_rule_overrides
from app.optimizer.rule_registry import ALL_KNOWN_RULE_IDS, is_known_rule, rule_engine_tier
from app.optimizer.rules import DEFAULT_RULES


def test_all_cost_export_rules_in_registry():
    for rule in COST_EXPORT_RULES_BY_ID.values():
        assert is_known_rule(rule.id)
        assert rule_engine_tier(rule.id) == "cost_export"


def test_catalog_includes_cost_export_rules():
    catalog_ids = {r["id"] for r in list_all_rules()}
    for rule_id in COST_EXPORT_RULES_BY_ID:
        assert rule_id in catalog_ids


def test_cost_export_rule_has_configurable_settings():
    rule = COST_EXPORT_RULES_BY_ID["COST_HIGH_SPEND_REVIEW"]
    serialized = serialize_cost_export_rule(rule)
    keys = {s["key"] for s in serialized["settings"]}
    assert serialized["engine"] == "cost_export"
    assert "min_monthly_cost" in keys
    assert "savings_factor" in keys


def test_disabled_cost_export_rule_skipped():
    rows = [{
        "id": "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        "name": "vm1",
        "type": "compute/vm",
        "monthlyCostBilling": 600.0,
    }]
    overrides = {"COST_HIGH_SPEND_REVIEW": {"enabled": False}}
    active_ids = {r.id for r in effective_cost_export_rules(overrides)}
    assert "COST_HIGH_SPEND_REVIEW" not in active_ids
    findings = analyze_cost_export_resources("sub-id", rows, rule_overrides=overrides)
    assert not any(f["rule_id"] == "COST_HIGH_SPEND_REVIEW" for f in findings)


def test_min_monthly_cost_override():
    rows = [{
        "id": "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        "name": "vm1",
        "type": "compute/vm",
        "monthlyCostBilling": 400.0,
    }]
    default_findings = analyze_cost_export_resources("sub-id", rows)
    assert not any(f["rule_id"] == "COST_HIGH_SPEND_REVIEW" for f in default_findings)

    lowered = analyze_cost_export_resources(
        "sub-id",
        rows,
        rule_overrides={"COST_HIGH_SPEND_REVIEW": {"min_monthly_cost": 300.0}},
    )
    assert any(f["rule_id"] == "COST_HIGH_SPEND_REVIEW" for f in lowered)


def test_known_rule_count_covers_engines():
    assert len(ALL_KNOWN_RULE_IDS) >= 80


def test_disk_extended_rules_expose_metric_threshold_settings():
    by_id = {r["id"]: r for r in list_all_rules()}
    unused_keys = {s["key"] for s in by_id["DISK_UNUSED_EXTENDED"]["settings"]}
    assert {"max_unattached_disk_days", "disk_io_idle_bps", "disk_idle_min_size_gb", "disk_iops_block_downgrade_pct"} <= unused_keys
    oversize_keys = {s["key"] for s in by_id["DISK_OVERSIZE_EXTENDED"]["settings"]}
    assert {"disk_io_idle_bps", "disk_iops_block_downgrade_pct"} <= oversize_keys
    under_keys = {s["key"] for s in by_id["DISK_UNDERPROVISIONED"]["settings"]}
    assert "disk_iops_high_util_pct" in under_keys


def test_snapshot_rules_expose_retention_settings():
    by_id = {r["id"]: r for r in list_all_rules()}
    old_keys = {s["key"] for s in by_id["SNAPSHOT_OLD"]["settings"]}
    assert {"snapshot_retention_days", "snapshot_min_size_gb"} <= old_keys
    ext_keys = {s["key"] for s in by_id["SNAPSHOT_RETENTION_EXTENDED"]["settings"]}
    assert {"snapshot_retention_days", "snapshot_min_size_gb", "min_monthly_savings_usd"} <= ext_keys


def test_acr_rules_expose_threshold_settings():
    by_id = {r["id"]: r for r in list_all_rules()}
    premium_keys = {s["key"] for s in by_id["ACR_PREMIUM_EXTENDED"]["settings"]}
    assert {"acr_pull_count_low", "acr_storage_high_gb", "nonprod_tag_values", "min_monthly_savings_usd"} <= premium_keys
    storage_keys = {s["key"] for s in by_id["ACR_STORAGE_HIGH_EXTENDED"]["settings"]}
    assert {"acr_storage_high_gb", "acr_pull_count_low", "acr_push_count_low"} <= storage_keys
    assert "ACR_STANDARD_EXTENDED" in by_id
    assert "ACR_RETENTION_DISABLED_EXTENDED" in by_id


def test_keyvault_rules_expose_threshold_settings():
    by_id = {r["id"]: r for r in list_all_rules()}
    idle_keys = {s["key"] for s in by_id["KEYVAULT_IDLE_EXTENDED"]["settings"]}
    assert {"kv_api_hits_idle", "min_monthly_savings_usd"} <= idle_keys
    premium_keys = {s["key"] for s in by_id["KEYVAULT_PREMIUM_EXTENDED"]["settings"]}
    assert {"kv_api_hits_idle", "nonprod_tag_values", "min_monthly_savings_usd"} <= premium_keys
    high_keys = {s["key"] for s in by_id["KEYVAULT_HIGH_OPS_EXTENDED"]["settings"]}
    assert {"kv_api_hits_high", "min_monthly_savings_usd"} <= high_keys


def test_private_dns_rule_exposes_record_set_threshold():
    by_id = {r["id"]: r for r in list_all_rules()}
    keys = {s["key"] for s in by_id["PRIVATE_DNS_EMPTY_EXTENDED"]["settings"]}
    assert "private_dns_max_default_record_sets" in keys
    threshold = next(
        s for s in by_id["PRIVATE_DNS_EMPTY_EXTENDED"]["settings"]
        if s["key"] == "private_dns_max_default_record_sets"
    )
    assert threshold["default"] == 2


def test_all_rules_expose_severity_setting():
    for rule in list_all_rules():
        keys = {s["key"] for s in rule["settings"]}
        assert "severity" in keys, rule["id"]
        sev = next(s for s in rule["settings"] if s["key"] == "severity")
        assert sev["type"] == "select"
        assert sev["default"] == rule["severity"]


def test_apply_rule_overrides_coerces_severity_enum():
    rule = copy.deepcopy(DEFAULT_RULES["VM_IDLE"])
    apply_rule_overrides(rule, {"severity": "LOW"})
    assert rule.severity.value == "LOW"


def test_standard_engine_severity_override_on_finding():
    engine = OptimizationEngine(rule_overrides={"VM_IDLE": {"severity": "CRITICAL"}})
    rule = engine.rules["VM_IDLE"]
    finding = Finding(
        rule,
        {"id": "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1", "name": "vm1", "type": "compute/vm"},
        "detail",
        "recommendation",
    )
    assert finding.severity == "CRITICAL"


def test_cost_export_severity_override():
    rows = [{
        "id": "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        "name": "vm1",
        "type": "compute/vm",
        "monthlyCostBilling": 600.0,
    }]
    findings = analyze_cost_export_resources(
        "sub-id",
        rows,
        rule_overrides={"COST_HIGH_SPEND_REVIEW": {"severity": "CRITICAL", "min_monthly_cost": 300.0}},
    )
    match = [f for f in findings if f["rule_id"] == "COST_HIGH_SPEND_REVIEW"]
    assert match
    assert match[0]["severity"] == "CRITICAL"
