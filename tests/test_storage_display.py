"""Tests for storage display and human-readable evidence."""

from app.storage_display import (
    format_access_tier,
    format_replication_sku,
    format_storage_fact,
    make_storage_check,
    missing_display,
)
from app.resource_utilization import is_low_storage_utilization


def test_missing_vs_zero_capacity():
    assert format_storage_fact("used_capacity_bytes", None) == missing_display()
    assert format_storage_fact("used_capacity_bytes", 0) == "0 GB used"
    assert format_storage_fact("transaction_count", None) == missing_display()
    assert format_storage_fact("transaction_count", 0) == "0 transactions"


def test_replication_and_tier_labels():
    assert format_access_tier("Hot") == "Hot"
    assert "geo-redundant" in format_replication_sku("STANDARD_GRS").lower()


def test_low_storage_utilization_distinguishes_missing_and_zero():
    assert is_low_storage_utilization({"_technical_facts": {"used_capacity_bytes": None}}) is None
    assert is_low_storage_utilization({"_technical_facts": {"used_capacity_bytes": 0}}) is False
    assert is_low_storage_utilization({"_technical_facts": {"storage_pct": 10}}) is True


def test_make_storage_check_missing_is_not_synced():
    check = make_storage_check("Monthly egress", "egress_bytes", None, "≥ 100 GB/month", passed=False)
    assert check["status"] == "na"
    assert check["value_display"] == missing_display()


def test_make_storage_check_formats_bytes():
    check = make_storage_check(
        "Monthly egress",
        "egress_bytes",
        200_000_000_000,
        "≥ 100 GB/month",
        passed=True,
    )
    assert "GB" in check["value_display"]
    assert check["threshold_display"] == "≥ 100 GB/month"
