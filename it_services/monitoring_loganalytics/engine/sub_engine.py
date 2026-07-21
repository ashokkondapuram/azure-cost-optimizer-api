"""Sub-engine — owned by monitoring-loganalytics IT service."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.monitoring_loganalytics.engine.analysis import analyze_log_analytics


class LogAnalyticsSubEngine(ResourceSubEngine):
    component = 'Log Analytics workspace'
    bucket_keys = ('log_analytics_workspaces',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        resources = self.prepare_resources(buckets.get("log_analytics_workspaces") or [])
        findings = analyze_log_analytics(self.engine, self.ctx.subscription_id, resources, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, resources)
