"""Tests for centralized rule behavior wiring."""

from __future__ import annotations

from app.idle_resource_rules import is_idle_or_waste_rule
from app.optimizer.advanced_rules import ADVANCED_RULES
from app.rule_behavior import (
    SCORING_DECOMMISSION,
    SCORING_RESIZE_DOWN,
    classify_rule_action_class,
    get_rule_behavior,
    is_waste_heatmap_rule,
    scoring_action_for_rule_ids,
)
from app.savings_aggregation import SavingsActionClass, classify_engine_finding
from types import SimpleNamespace


def _finding(rule_id: str, savings: float = 50.0) -> SimpleNamespace:
    return SimpleNamespace(
        status="open",
        rule_id=rule_id,
        rule_name=rule_id,
        category="NETWORK",
        detail="",
        recommendation="",
        estimated_savings_usd=savings,
        evidence_json="{}",
    )


def test_network_idle_rules_on_waste_heatmap():
    for rule_id in (
        "PUBLIC_IP_IDLE_EXTENDED",
        "LOAD_BALANCER_IDLE_EXTENDED",
        "NAT_GATEWAY_IDLE_EXTENDED",
        "APP_GATEWAY_IDLE_EXTENDED",
        "NIC_ORPHANED_EXTENDED",
    ):
        assert is_waste_heatmap_rule(rule_id), rule_id
        assert is_idle_or_waste_rule(rule_id), rule_id


def test_rightsize_rules_not_on_waste_heatmap():
    for rule_id in (
        "VM_SKU_SIZING_EXTENDED",
        "DISK_CAPACITY_RIGHTSIZE_EXTENDED",
        "LOAD_BALANCER_THROUGHPUT_RIGHTSIZE",
        "VNET_PEERING_CONSOLIDATION_EXTENDED",
        "VMSS_AUTOSCALE_TUNING_EXTENDED",
    ):
        assert not is_waste_heatmap_rule(rule_id), rule_id


def test_idle_network_rules_classify_as_decommission():
    for rule_id in (
        "PUBLIC_IP_IDLE_EXTENDED",
        "LOAD_BALANCER_IDLE_EXTENDED",
        "NAT_GATEWAY_IDLE_EXTENDED",
    ):
        assert classify_rule_action_class(rule_id) == SavingsActionClass.DECOMMISSION
        assert classify_engine_finding(_finding(rule_id)) == SavingsActionClass.DECOMMISSION


def test_compute_rightsize_classifies_correctly():
    assert classify_rule_action_class("VMSS_AUTOSCALE_TUNING_EXTENDED") == SavingsActionClass.RIGHTSIZE
    assert classify_rule_action_class("AKS_POD_DENSITY_EXTENDED") == SavingsActionClass.RIGHTSIZE
    assert classify_rule_action_class("SNAPSHOT_ARCHIVE_EXTENDED") == SavingsActionClass.DECOMMISSION


def test_performance_rules_not_on_heatmap():
    for rule_id in (
        "LOAD_BALANCER_SNAT_PRESSURE",
        "NAT_GATEWAY_SNAT_EXHAUSTION",
        "VM_MEMORY_PRESSURE_EXTENDED",
    ):
        assert not is_waste_heatmap_rule(rule_id)
        assert classify_rule_action_class(rule_id) == SavingsActionClass.NON_COST


def test_scoring_action_for_idle_network_rules():
    action = scoring_action_for_rule_ids({
        "PUBLIC_IP_IDLE_EXTENDED",
        "LOAD_BALANCER_THROUGHPUT_RIGHTSIZE",
    })
    assert action == SCORING_DECOMMISSION


def test_scoring_action_prefers_manual_review_over_decommission():
    action = scoring_action_for_rule_ids({
        "PUBLIC_IP_IDLE_EXTENDED",
        "LOAD_BALANCER_SNAT_PRESSURE",
    })
    assert action == "manual_review"


def test_legacy_alias_resolves_to_canonical_behavior():
    behavior = get_rule_behavior("IP_UNASSOCIATED")
    assert behavior is not None
    assert behavior.action_class == SavingsActionClass.DECOMMISSION.value
    assert behavior.waste_heatmap is True


def test_every_advanced_rule_has_behavior():
    missing = [rid for rid in ADVANCED_RULES if get_rule_behavior(rid) is None]
    assert not missing, f"Rules missing behavior inference: {missing[:10]}"
