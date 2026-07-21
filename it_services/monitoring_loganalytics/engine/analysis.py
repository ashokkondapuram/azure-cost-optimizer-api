"""Analysis rules — owned by monitoring-loganalytics IT service."""

from __future__ import annotations

from typing import Any

from app.cost_utils import resource_cost
from app.optimizer.core.finding import ExtendedFinding
from app.stub_engine_common import append_stub_draft
from it_services.monitoring_loganalytics.engine.optimization_rules import (
    evaluate_log_analytics_high_ingestion,
    evaluate_log_analytics_retention,
)


def analyze_log_analytics(
    engine,
    subscription_id: str,
    workspaces: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    retention_rule = engine.rules.get("LOG_ANALYTICS_RETENTION_EXTENDED")
    ingestion_rule = engine.rules.get("LOG_ANALYTICS_INGESTION_EXTENDED")
    for ws in workspaces:
        monthly = resource_cost(cost_by_resource, ws.get("id", ""))
        append_stub_draft(out, engine, subscription_id, ws, retention_rule, evaluate_log_analytics_retention(ws, monthly, retention_rule))
        append_stub_draft(out, engine, subscription_id, ws, ingestion_rule, evaluate_log_analytics_high_ingestion(ws, monthly, ingestion_rule))
    return out
