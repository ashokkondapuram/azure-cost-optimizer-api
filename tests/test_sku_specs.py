"""Tests for per-service SKU specification loader."""

from __future__ import annotations

from it_services.sku_specs import load_sku_specs_for_canonical, sku_summary


def test_compute_disk_sku_specs_loaded():
    spec = load_sku_specs_for_canonical("compute/disk")
    assert spec.get("canonical_type") == "compute/disk"
    skus = spec.get("skus") or {}
    assert "Premium_LRS" in skus
    assert spec.get("pricing")


def test_network_nat_sku_specs_from_azure_docs():
    spec = load_sku_specs_for_canonical("network/nat")
    skus = spec.get("skus") or {}
    assert "Standard" in skus
    assert skus["Standard"].get("snat_ports_per_ip") == 64512


def test_sku_summary_compact():
    spec = load_sku_specs_for_canonical("compute/vm")
    summary = sku_summary(spec)
    assert summary.get("canonical_type") == "compute/vm"
    assert summary.get("sku_count", 0) > 0
