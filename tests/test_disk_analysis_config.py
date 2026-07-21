"""Tests for managed disk extended analysis spec and Azure-billed savings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT_PATH = ROOT / "data" / "disk-assessment.json"


def test_disk_assessment_has_all_analysis_rules():
    spec = json.loads(ASSESSMENT_PATH.read_text(encoding="utf-8"))
    rule_ids = {r["rule_id"] for r in spec.get("rules") or []}
    expected = {
        "DISK_UNATTACHED",
        "DISK_OVERSIZE",
        "DISK_UNUSED_EXTENDED",
        "DISK_OVERSIZE_EXTENDED",
        "DISK_UNDERPROVISIONED",
        "DISK_CAPACITY_RIGHTSIZE_EXTENDED",
        "DISK_QUEUE_DEPTH_EXTENDED",
        "DISK_NEW_GRACE_PERIOD",
        "DISK_ULTRA_DOWNGRADE_PREMIUM",
        "DISK_ULTRA_DOWNGRADE_SSD",
        "DISK_PREMIUM_DOWNGRADE_HDD",
        "DISK_SSD_DOWNGRADE_HDD",
    }
    assert expected.issubset(rule_ids)
    assert spec.get("cost_policy", {}).get("source") == "azure_cost_management"
    assert "optimization_thresholds" in spec


def test_disk_savings_prefers_billed_mtd():
    from app.pricing.savings_calculator import savings_from_disk_pricing

    savings = savings_from_disk_pricing(None, billed_mtd=42.5, full_baseline_for_delete=True)
    assert savings == 42.5


def test_disk_tier_savings_uses_billed_when_retail_missing(monkeypatch):
    from app.azure_retail_pricing import estimate_disk_tier_savings

    monkeypatch.setattr(
        "app.azure_retail_pricing.get_managed_disk_monthly_price",
        lambda *a, **k: None,
    )
    pricing = estimate_disk_tier_savings(
        "canadacentral",
        512,
        "Premium_LRS",
        "StandardSSD_LRS",
        actual_monthly_cost=120.0,
    )
    assert pricing["pricing_source"] == "azure_billed_mtd"
    assert pricing["estimated_monthly_savings_usd"] > 0


def test_extended_disk_rules_registered():
    from app.optimizer.extended_engine import ExtendedOptimizationEngine
    from it_services.compute_disk.assessment_bridge import disk_rule_ids, optimization_thresholds

    engine = ExtendedOptimizationEngine()
    for rule_id in (
        "DISK_ULTRA_DOWNGRADE_PREMIUM",
        "DISK_ULTRA_DOWNGRADE_SSD",
        "DISK_PREMIUM_DOWNGRADE_HDD",
        "DISK_SSD_DOWNGRADE_HDD",
        "DISK_NEW_GRACE_PERIOD",
    ):
        assert rule_id in engine.rules
    assert len(disk_rule_ids()) >= 12
    assert optimization_thresholds().get("disk_io_idle_bps") == 1024.0


def test_extended_disk_spec_from_assessment():
    from it_services.compute_disk.assessment_bridge import extended_disk_spec_payload

    payload = extended_disk_spec_payload()
    assert payload["assessment_file"] == "disk-assessment.json"
    assert payload["schema_version"] == "2.0"
    assert len(payload.get("analysis_rules") or []) >= 12
    assert payload.get("cost_source") == "azure_cost_management"


def test_compute_disk_service_extended_rules_endpoint():
    import importlib.util
    from fastapi.testclient import TestClient

    service_src = ROOT / "services" / "resources" / "compute-disk" / "src" / "service_app.py"
    spec = importlib.util.spec_from_file_location("compute_disk_service_app", service_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    client = TestClient(module.app)
    res = client.get("/v1/rules/extended")
    assert res.status_code == 200
    body = res.json()
    assert body["canonical_type"] == "compute/disk"
    assert len(body.get("analysis_rules") or []) >= 12
    assert body.get("cost_source") == "azure_cost_management"
