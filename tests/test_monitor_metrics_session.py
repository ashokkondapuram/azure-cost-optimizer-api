"""Thread-safety tests for parallel Azure Monitor metrics fetch."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from app.monitor_metrics import load_azure_monitor_metrics


def test_parallel_monitor_fetch_uses_pinned_token_not_shared_db_session():
    """Worker threads must not call Azure APIs with the caller's SQLAlchemy session."""
    db = MagicMock(name="caller_session")
    resources = {
        "database/cosmosdb": [
            {
                "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.DocumentDB/databaseAccounts/a1",
                "name": "a1",
            },
            {
                "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.DocumentDB/databaseAccounts/a2",
                "name": "a2",
            },
        ],
    }
    observed_db_args: list = []

    class _Client:
        def __init__(self, db=None):
            self._db = db

        def get_resource_metrics(
            self,
            resource_id,
            metric_names,
            timespan="PT1H",
            interval="PT1H",
            aggregation="Average",
            db=None,
        ):
            observed_db_args.append(db)
            return {
                "value": [
                    {
                        "name": {"value": metric_names[0]},
                        "timeseries": [{"data": [{"total": 42.0}]}],
                    }
                ]
            }

    @contextmanager
    def _fake_arm_auth_context(*, db=None, token=None):
        yield

    profile = MagicMock()
    profile.metrics = [MagicMock(timespan="P7D")]
    profile.metric_names.return_value = ("TotalRequests",)
    profile.aggregations.return_value = "Total"

    with (
        patch("app.monitor_metrics.RESOURCE_MONITOR_PROFILES", {True: True}),
        patch("app.monitor_metrics.get_monitor_profile", return_value=profile),
        patch("app.monitor_metrics._max_workers", return_value=2),
        patch("app.monitor_metrics.monitor_max_retries", return_value=0),
        patch("app.monitor_metrics.monitor_fetch_timeout_sec", return_value=5),
        patch("app.azure_resources.AzureResourcesClient", _Client),
        patch("app.auth.get_token", return_value="pinned-token"),
        patch("app.auth.arm_auth_context", _fake_arm_auth_context),
    ):
        metrics, _facts, stats = load_azure_monitor_metrics(
            resources,
            {},
            db=db,
            max_workers=2,
            max_retries=0,
        )

    assert stats["loaded"] == 2
    assert len(metrics) == 2
    assert observed_db_args
    assert all(arg is None for arg in observed_db_args)


def test_metrics_loader_parallel_tasks_use_separate_sessions():
    """K8s and monitor loaders must not share one Session across ThreadPool workers."""
    created_sessions: list = []

    class _Session:
        def close(self):
            pass

    def _session_factory():
        session = _Session()
        created_sessions.append(session)
        return session

    buckets = {"aks_clusters": [], "vms": []}
    with (
        patch("app.database.SessionLocal", side_effect=_session_factory),
        patch("app.metrics_loader.load_k8s_node_metrics", return_value={}),
        patch("app.metrics_loader.load_azure_monitor_metrics", return_value=({}, {}, {})),
        patch("app.metrics_loader.group_resources_by_canonical_type", return_value={}),
    ):
        from app.metrics_loader import load_analysis_metrics

        load_analysis_metrics(MagicMock(), buckets=buckets, cost_by_resource={})

    assert len(created_sessions) == 2
    assert created_sessions[0] is not created_sessions[1]
