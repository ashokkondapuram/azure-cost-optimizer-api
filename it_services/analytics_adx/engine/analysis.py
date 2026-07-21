"""Analysis rules — owned by analytics-adx IT service."""

from __future__ import annotations

from typing import Any

from app.cost_utils import resource_cost
from app.optimizer.core.finding import ExtendedFinding
from app.stub_engine_common import append_stub_draft
from it_services.analytics_adx.engine.optimization_rules import (
    evaluate_adx_ingestion_cost,
    evaluate_adx_low_ingestion,
)


def analyze_adx(
    engine,
    subscription_id: str,
    clusters: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    ingestion_rule = engine.rules.get("ADX_INGESTION_EXTENDED")
    low_rule = engine.rules.get("ADX_LOW_INGESTION_EXTENDED")
    for cluster in clusters:
        monthly = resource_cost(cost_by_resource, cluster.get("id", ""))
        append_stub_draft(out, engine, subscription_id, cluster, ingestion_rule, evaluate_adx_ingestion_cost(cluster, monthly, ingestion_rule))
        append_stub_draft(out, engine, subscription_id, cluster, low_rule, evaluate_adx_low_ingestion(cluster, monthly, low_rule))
    return out
