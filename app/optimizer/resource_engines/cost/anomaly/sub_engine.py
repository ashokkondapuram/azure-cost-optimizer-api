"""Cost anomaly optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.resource_engines.cost.anomaly.analysis import analyze_cost_anomalies
from app.optimizer.resource_engines.runtime.base import ResourceSubEngine


class CostAnomalySubEngine(ResourceSubEngine):
    component = "Cost Anomalies"
    bucket_keys = ("cost_anomalies",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        if not self.ctx.cost_history:
            return []
        return analyze_cost_anomalies(
            self.engine,
            self.ctx.subscription_id,
            self.ctx.cost_history,
        )
