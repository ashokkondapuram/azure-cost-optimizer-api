"""Analytics optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.resource_engines.runtime.base import ResourceSubEngine
from app.optimizer.resource_engines.analytics.analysis import (
    analyze_adx,
    analyze_databricks,
    analyze_ml_workspaces,
    analyze_synapse,
)


class AnalyticsSubEngine(ResourceSubEngine):
    component = "Analytics"
    bucket_keys = ("databricks_workspaces", "synapse_workspaces", "adx_clusters", "ml_workspaces")

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        databricks = self.prepare_resources(buckets.get("databricks_workspaces") or [])
        synapse = self.prepare_resources(buckets.get("synapse_workspaces") or [])
        adx = self.prepare_resources(buckets.get("adx_clusters") or [])
        ml = self.prepare_resources(buckets.get("ml_workspaces") or [])
        findings = analyze_databricks(self.engine, self.ctx.subscription_id, databricks, self.ctx.cost_by_resource)
        findings.extend(analyze_synapse(self.engine, self.ctx.subscription_id, synapse, self.ctx.cost_by_resource))
        findings.extend(analyze_adx(self.engine, self.ctx.subscription_id, adx, self.ctx.cost_by_resource))
        findings.extend(analyze_ml_workspaces(self.engine, self.ctx.subscription_id, ml, self.ctx.cost_by_resource))
        return self.enhance_findings(findings, databricks + synapse + adx + ml)
