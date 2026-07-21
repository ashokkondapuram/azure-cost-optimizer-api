"""Tests for assessment vs legacy sub-engine routing."""

from __future__ import annotations

from app.optimizer.analysis_routing import (
    PLATFORM_SUB_ENGINE_NAMES,
    filter_buckets_for_legacy_analysis,
    filter_resources_for_legacy,
    integrated_sub_engines_enabled,
    should_run_sub_engine,
)


class _FakeEngine:
    def __init__(self, name: str):
        self.__name__ = name


def test_integrated_sub_engines_enabled_by_default(monkeypatch):
    monkeypatch.delenv("LEGACY_SUB_ENGINES_ENABLED", raising=False)
    assert integrated_sub_engines_enabled() is True


def test_platform_sub_engine_always_runs(monkeypatch):
    monkeypatch.setenv("ASSESSMENT_PIPELINE_ENABLED", "true")
    monkeypatch.delenv("LEGACY_SUB_ENGINES_ENABLED", raising=False)
    budget = _FakeEngine("BudgetSubEngine")
    disk = _FakeEngine("DiskSubEngine")
    assert should_run_sub_engine(budget) is True
    assert should_run_sub_engine(disk) is True


def test_resource_sub_engine_disabled_when_opted_out(monkeypatch):
    monkeypatch.setenv("ASSESSMENT_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("LEGACY_SUB_ENGINES_ENABLED", "false")
    disk = _FakeEngine("DiskSubEngine")
    assert should_run_sub_engine(disk) is False


def test_platform_names_cover_budget_anomaly_commitments():
    assert "BudgetSubEngine" in PLATFORM_SUB_ENGINE_NAMES
    assert "CostAnomalySubEngine" in PLATFORM_SUB_ENGINE_NAMES
    assert "CommitmentsSubEngine" in PLATFORM_SUB_ENGINE_NAMES


def test_filter_buckets_keeps_indexed_disks_by_default(monkeypatch):
    monkeypatch.setenv("ASSESSMENT_PIPELINE_ENABLED", "true")
    monkeypatch.delenv("LEGACY_SUB_ENGINES_ENABLED", raising=False)
    disk = {
        "id": "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/d1",
        "name": "d1",
    }
    buckets = {
        "disks": [disk],
        "budgets": [{"name": "monthly"}],
    }
    filtered = filter_buckets_for_legacy_analysis(buckets)
    assert filtered["disks"] == buckets["disks"]
    assert filtered["budgets"] == buckets["budgets"]


def test_filter_buckets_removes_indexed_disks_when_disabled(monkeypatch):
    monkeypatch.setenv("ASSESSMENT_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("LEGACY_SUB_ENGINES_ENABLED", "false")
    disk = {
        "id": "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/d1",
        "name": "d1",
    }
    buckets = {
        "disks": [disk],
        "budgets": [{"name": "monthly"}],
    }
    filtered = filter_buckets_for_legacy_analysis(buckets)
    assert filtered["disks"] == []
    assert filtered["budgets"] == buckets["budgets"]


def test_filter_buckets_preserves_scoped_cosmos_when_sub_engines_disabled(monkeypatch):
    monkeypatch.setenv("ASSESSMENT_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("LEGACY_SUB_ENGINES_ENABLED", "false")
    cosmos = {
        "id": "/subscriptions/sub/resourcegroups/rg/providers/Microsoft.DocumentDB/databaseAccounts/c1",
        "name": "c1",
        "type": "Microsoft.DocumentDB/databaseAccounts",
    }
    buckets = {"cosmosdb": [cosmos], "disks": [{"id": "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/d1"}]}
    filtered = filter_buckets_for_legacy_analysis(
        buckets,
        preserve_canonical_types={"database/cosmosdb"},
    )
    assert filtered["cosmosdb"] == [cosmos]
    assert filtered["disks"] == []


def test_filter_resources_keeps_non_indexed_when_disabled(monkeypatch):
    monkeypatch.setenv("ASSESSMENT_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("LEGACY_SUB_ENGINES_ENABLED", "false")
    custom = {"id": "/subscriptions/sub/resourcegroups/rg/providers/custom.vendor/widgets/w1"}
    kept = filter_resources_for_legacy([custom])
    assert kept == [custom]
