"""Tests for backend architecture improvements."""

from __future__ import annotations

from app.optimizer.workload_classifier import classify_workload, downsize_allowed_for_workload
from app.parallel_arm_sync import parallel_fetch
from app.perf_cache import cached_cost_map, invalidate_subscription
from app.recommendation_execution import escalate_persisted_findings_after_execution


def test_workload_classifier_batch():
    facts = {"avg_cpu_pct": 10.0, "max_cpu_pct": 45.0}
    assert classify_workload({}, facts) == "batch"


def test_workload_classifier_zombie():
    facts = {"avg_cpu_pct": 1.0, "max_cpu_pct": 2.0, "avg_disk_iops": 10}
    assert classify_workload({}, facts) == "zombie"


def test_downsize_allowed_batch_uses_peak_only():
    facts = {"avg_cpu_pct": 8.0, "max_cpu_pct": 12.0}
    assert downsize_allowed_for_workload("batch", facts, avg_threshold=15.0) is True
    assert downsize_allowed_for_workload("batch", facts, avg_threshold=10.0) is False


def test_downsize_blocked_for_zombie():
    facts = {"avg_cpu_pct": 1.0, "max_cpu_pct": 2.0}
    assert downsize_allowed_for_workload("zombie", facts, avg_threshold=15.0) is False


def test_parallel_fetch():
    calls = []

    def make(n):
        def fn():
            calls.append(n)
            return [n]
        return fn

    out = parallel_fetch([("a", make(1)), ("b", make(2)), ("c", make(3))], max_workers=3)
    assert sorted(out.keys()) == ["a", "b", "c"]
    assert len(calls) == 3


def test_perf_cache_invalidate_subscription():
    from app.cost_query_cache import cached_cost_live_query, cost_cache_metrics

    key = "cost_map:sub-abc"
    cached_cost_map(key, lambda: {"x": 1})
    cached_cost_live_query("sub-abc", "summary", "MonthToDate", lambda: {"pretax_total": 9})
    assert cost_cache_metrics()["entries"] == 1
    invalidate_subscription("sub-abc")
    assert cost_cache_metrics()["entries"] == 0
    assert cached_cost_map(key, lambda: {"x": 2}) == {"x": 2}
