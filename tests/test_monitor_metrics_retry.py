"""Tests for Azure Monitor metrics retry helpers and fetch orchestration."""

from __future__ import annotations

import time
from concurrent import futures
from unittest.mock import MagicMock, patch

import pytest

from app.http_client import AzureAPIError
from app.monitor_metrics import _call_with_timeout, load_azure_monitor_metrics
from app.monitor_metrics_retry import (
    is_retryable_fetch_error,
    is_retryable_http_status,
    monitor_max_retries,
    retry_backoff_seconds,
)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (429, True),
        (500, True),
        (502, True),
        (503, True),
        (504, True),
        (403, False),
        (404, False),
        (400, False),
        (200, False),
    ],
)
def test_is_retryable_http_status(status, expected):
    assert is_retryable_http_status(status) is expected


@pytest.mark.parametrize(
    ("err", "expected"),
    [
        (None, False),
        ("empty", False),
        ("timed_out", True),
        ("503:ConnectionError", True),
        ("429:Retryable", True),
        ("504:Timeout", True),
        ("403:AuthorizationFailed", False),
        ("404:ResourceNotFound", False),
        ("Connection reset by peer", True),
        ("some validation error", False),
    ],
)
def test_is_retryable_fetch_error(err, expected):
    assert is_retryable_fetch_error(err) is expected


def test_retry_backoff_seconds_grows_with_attempt(monkeypatch):
    monkeypatch.setenv("ANALYSIS_MONITOR_METRICS_RETRY_BACKOFF_SEC", "2")
    monkeypatch.setenv("ANALYSIS_MONITOR_METRICS_RETRY_BACKOFF_MAX_SEC", "30")
    first = retry_backoff_seconds(0)
    second = retry_backoff_seconds(1)
    assert 2.0 <= first <= 3.0
    assert 4.0 <= second <= 6.0
    assert second > first


def test_monitor_max_retries_env(monkeypatch):
    monkeypatch.setenv("ANALYSIS_MONITOR_METRICS_MAX_RETRIES", "5")
    assert monitor_max_retries() == 5


def test_call_with_timeout_raises_on_slow_call():
    def _slow() -> str:
        time.sleep(0.2)
        return "ok"

    with pytest.raises(futures.TimeoutError):
        _call_with_timeout(_slow, 0.05)


def test_call_with_timeout_returns_on_fast_call():
    assert _call_with_timeout(lambda: "ok", 1.0) == "ok"


def _sample_payload() -> dict:
    return {
        "value": [
            {
                "name": {"value": "Percentage CPU"},
                "timeseries": [{"data": [{"average": 12.5}]}],
            },
        ],
    }


def _vm_resource() -> dict:
    return {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
    }


@patch("app.monitor_metrics.RESOURCE_MONITOR_PROFILES", {"microsoft.compute/virtualmachines": MagicMock()})
@patch("app.monitor_metrics.get_monitor_profile")
@patch("app.auth.get_token")
@patch("app.auth.arm_auth_context")
@patch("app.azure_resources.AzureResourcesClient")
def test_load_azure_monitor_metrics_retries_transient_error(
    mock_client_cls,
    mock_auth_ctx,
    mock_get_token,
    mock_get_profile,
    monkeypatch,
):
    monkeypatch.setenv("ANALYSIS_MONITOR_METRICS_MAX_RETRIES", "2")
    monkeypatch.setenv("ANALYSIS_MONITOR_METRICS_RETRY_BACKOFF_SEC", "0.01")
    monkeypatch.setenv("ANALYSIS_MONITOR_METRICS_RETRY_BACKOFF_MAX_SEC", "0.05")
    monkeypatch.setenv("ANALYSIS_MONITOR_METRICS_TIMEOUT_SEC", "5")

    profile = MagicMock()
    profile.metrics = [MagicMock(timespan="P7D")]
    profile.metric_names.return_value = ("Percentage CPU",)
    profile.aggregations.return_value = "Average"
    mock_get_profile.return_value = profile

    client = MagicMock()
    client.get_resource_metrics.side_effect = [
        AzureAPIError(503, "ServiceUnavailable", "busy"),
        AzureAPIError(503, "ServiceUnavailable", "still busy"),
        _sample_payload(),
    ]
    mock_client_cls.return_value = client
    mock_auth_ctx.return_value.__enter__ = MagicMock(return_value=None)
    mock_auth_ctx.return_value.__exit__ = MagicMock(return_value=False)

    metrics, facts, stats = load_azure_monitor_metrics(
        {"compute/vm": [_vm_resource()]},
        {},
        db=MagicMock(),
    )

    assert client.get_resource_metrics.call_count == 3
    assert len(metrics) == 1
    assert stats["loaded"] == 1
    assert stats["failed"] == 0
    assert stats["retried"] == 2
    assert stats["timed_out"] == 0


@patch("app.monitor_metrics.RESOURCE_MONITOR_PROFILES", {"microsoft.compute/virtualmachines": MagicMock()})
@patch("app.monitor_metrics.get_monitor_profile")
@patch("app.auth.get_token")
@patch("app.auth.arm_auth_context")
@patch("app.azure_resources.AzureResourcesClient")
def test_load_azure_monitor_metrics_does_not_retry_404(
    mock_client_cls,
    mock_auth_ctx,
    mock_get_token,
    mock_get_profile,
    monkeypatch,
):
    monkeypatch.setenv("ANALYSIS_MONITOR_METRICS_MAX_RETRIES", "3")
    monkeypatch.setenv("ANALYSIS_MONITOR_METRICS_RETRY_BACKOFF_SEC", "0.01")

    profile = MagicMock()
    profile.metrics = [MagicMock(timespan="P7D")]
    profile.metric_names.return_value = ("Percentage CPU",)
    profile.aggregations.return_value = "Average"
    mock_get_profile.return_value = profile

    client = MagicMock()
    client.get_resource_metrics.side_effect = AzureAPIError(404, "ResourceNotFound", "gone")
    mock_client_cls.return_value = client
    mock_auth_ctx.return_value.__enter__ = MagicMock(return_value=None)
    mock_auth_ctx.return_value.__exit__ = MagicMock(return_value=False)

    metrics, facts, stats = load_azure_monitor_metrics(
        {"compute/vm": [_vm_resource()]},
        {},
        db=MagicMock(),
    )

    assert client.get_resource_metrics.call_count == 1
    assert metrics == {}
    assert stats["failed"] == 1
    assert stats["not_found"] == 1
    assert stats["retried"] == 0


@patch("app.monitor_metrics.monitor_fetch_timeout_sec", return_value=1)
@patch("app.monitor_metrics.RESOURCE_MONITOR_PROFILES", {"microsoft.compute/virtualmachines": MagicMock()})
@patch("app.monitor_metrics.get_monitor_profile")
@patch("app.auth.get_token")
@patch("app.auth.arm_auth_context")
@patch("app.azure_resources.AzureResourcesClient")
def test_load_azure_monitor_metrics_retries_timeout(
    mock_client_cls,
    mock_auth_ctx,
    mock_get_token,
    mock_get_profile,
    _mock_timeout,
    monkeypatch,
):
    monkeypatch.setenv("ANALYSIS_MONITOR_METRICS_MAX_RETRIES", "1")
    monkeypatch.setenv("ANALYSIS_MONITOR_METRICS_RETRY_BACKOFF_SEC", "0.01")

    profile = MagicMock()
    profile.metrics = [MagicMock(timespan="P7D")]
    profile.metric_names.return_value = ("Percentage CPU",)
    profile.aggregations.return_value = "Average"
    mock_get_profile.return_value = profile

    client = MagicMock()
    call_count = {"n": 0}

    def _side_effect(*_args, **_kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            time.sleep(1.5)
        return _sample_payload()

    client.get_resource_metrics.side_effect = _side_effect
    mock_client_cls.return_value = client
    mock_auth_ctx.return_value.__enter__ = MagicMock(return_value=None)
    mock_auth_ctx.return_value.__exit__ = MagicMock(return_value=False)

    metrics, facts, stats = load_azure_monitor_metrics(
        {"compute/vm": [_vm_resource()]},
        {},
        db=MagicMock(),
    )

    assert client.get_resource_metrics.call_count == 2
    assert len(metrics) == 1
    assert stats["loaded"] == 1
    assert stats["retried"] == 1
    assert stats["timed_out"] == 0


@patch("app.monitor_metrics.RESOURCE_MONITOR_PROFILES", {"microsoft.compute/virtualmachines": MagicMock()})
@patch("app.monitor_metrics.get_monitor_profile")
@patch("app.auth.get_token")
@patch("app.auth.arm_auth_context")
@patch("app.azure_resources.AzureResourcesClient")
def test_load_azure_monitor_metrics_sync_timeout_no_retry(
    mock_client_cls,
    mock_auth_ctx,
    mock_get_token,
    mock_get_profile,
    monkeypatch,
):
    monkeypatch.setenv("ANALYSIS_MONITOR_METRICS_MAX_RETRIES", "2")

    profile = MagicMock()
    profile.metrics = [MagicMock(timespan="P7D")]
    profile.metric_names.return_value = ("Percentage CPU",)
    profile.aggregations.return_value = "Average"
    mock_get_profile.return_value = profile

    client = MagicMock()

    def _slow(*_args, **_kwargs):
        time.sleep(1.5)
        return _sample_payload()

    client.get_resource_metrics.side_effect = _slow
    mock_client_cls.return_value = client
    mock_auth_ctx.return_value.__enter__ = MagicMock(return_value=None)
    mock_auth_ctx.return_value.__exit__ = MagicMock(return_value=False)

    metrics, facts, stats = load_azure_monitor_metrics(
        {"compute/vm": [_vm_resource()]},
        {},
        db=MagicMock(),
        fetch_timeout_sec=1,
        max_retries=0,
    )

    assert client.get_resource_metrics.call_count == 1
    assert metrics == {}
    assert stats["failed"] == 1
    assert stats["timed_out"] == 1
    assert stats["retried"] == 0


def test_filter_metrics_grouped_scoped_canonical():
    from app.assessment.metrics_collector import _filter_metrics_grouped

    grouped = {
        "database/cosmosdb": [{"id": "/subscriptions/s1/.../cosmos1"}],
        "compute/vm": [{"id": "/subscriptions/s1/.../vm1"}],
    }
    filtered = _filter_metrics_grouped(
        grouped,
        canonical_types={"database/cosmosdb"},
    )
    assert list(filtered.keys()) == ["database/cosmosdb"]
    assert len(filtered["database/cosmosdb"]) == 1


@patch("app.workers.inventory_metrics_worker.load_azure_monitor_metrics")
@patch("app.workers.inventory_metrics_worker.build_assessment_metrics_plan")
def test_inventory_metrics_worker_sync_context_overrides(mock_plan, mock_load, monkeypatch):
    from app.workers.inventory_metrics_worker import run_inventory_metrics_worker

    monkeypatch.setenv("SYNC_MONITOR_METRICS_TIMEOUT_SEC", "25")
    monkeypatch.setenv("SYNC_MONITOR_METRICS_MAX_RETRIES", "0")
    monkeypatch.setenv("SYNC_MONITOR_METRICS_MAX_WORKERS", "2")

    mock_plan.return_value = {
        "grouped": {"database/cosmosdb": [{"id": "/subscriptions/s1/.../cosmos1"}]},
        "metric_names_by_canonical": {},
        "required_keys_by_canonical": {},
        "assessment_by_canonical": {},
    }
    mock_load.return_value = ({}, {}, {"failed": 1, "timed_out": 1, "loaded": 0})

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    db.commit = MagicMock()

    result = run_inventory_metrics_worker(
        db,
        "s1",
        scoped_canonical_types=["database/cosmosdb"],
        sync_context=True,
    )

    assert result["status"] == "partial"
    assert result["metrics_timed_out"] == 1
    kwargs = mock_load.call_args.kwargs
    assert kwargs["fetch_timeout_sec"] == 25
    assert kwargs["max_retries"] == 0
    assert kwargs["max_workers"] == 2
    plan_kwargs = mock_plan.call_args.kwargs
    assert plan_kwargs["canonical_types"] == {"database/cosmosdb"}


@patch("app.monitor_metrics.enrich_derived_monitor_facts")
@patch("app.monitor_metrics.RESOURCE_MONITOR_PROFILES", {"microsoft.compute/virtualmachines": MagicMock()})
@patch("app.monitor_metrics.get_monitor_profile")
@patch("app.auth.get_token")
@patch("app.auth.arm_auth_context")
@patch("app.azure_resources.AzureResourcesClient")
def test_load_azure_monitor_metrics_continues_after_enrich_failure(
    mock_client_cls,
    mock_auth_ctx,
    mock_get_token,
    mock_get_profile,
    mock_enrich,
):
    profile = MagicMock()
    profile.metrics = [MagicMock(timespan="P7D")]
    profile.metric_names.return_value = ("Percentage CPU",)
    profile.aggregations.return_value = "Average"
    mock_get_profile.return_value = profile

    client = MagicMock()
    client.get_resource_metrics.return_value = _sample_payload()
    mock_client_cls.return_value = client
    mock_auth_ctx.return_value.__enter__ = MagicMock(return_value=None)
    mock_auth_ctx.return_value.__exit__ = MagicMock(return_value=False)

    resources = [
        {
            "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        },
        {
            "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm2",
        },
    ]
    mock_enrich.side_effect = [
        AttributeError("'str' object has no attribute 'get'"),
        {"avg_cpu_pct": 12.5},
    ]

    metrics, facts, stats = load_azure_monitor_metrics(
        {"compute/vm": resources},
        {},
        db=MagicMock(),
    )

    assert len(metrics) == 2
    assert mock_enrich.call_count == 2
    assert len(facts) == 1
    assert stats["loaded"] == 2
