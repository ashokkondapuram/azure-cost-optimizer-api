"""Sub-engine — owned by analytics-databricks IT service."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.analytics_databricks.engine.analysis import analyze_databricks


class DatabricksSubEngine(ResourceSubEngine):
    component = 'Azure Databricks'
    bucket_keys = ('databricks_workspaces',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        resources = self.prepare_resources(buckets.get("databricks_workspaces") or [])
        findings = analyze_databricks(self.engine, self.ctx.subscription_id, resources, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, resources)
