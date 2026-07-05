"""Monitoring optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.resource_engines.runtime.base import ResourceSubEngine
from app.optimizer.resource_engines.monitoring.analysis import analyze_app_insights, analyze_log_analytics


class MonitoringSubEngine(ResourceSubEngine):
    component = "Monitoring"
    bucket_keys = ("log_analytics_workspaces", "app_insights_components")

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        workspaces = self.prepare_resources(buckets.get("log_analytics_workspaces") or [])
        components = self.prepare_resources(buckets.get("app_insights_components") or [])
        findings = analyze_log_analytics(
            self.engine, self.ctx.subscription_id, workspaces, self.ctx.cost_by_resource,
        )
        findings.extend(analyze_app_insights(
            self.engine, self.ctx.subscription_id, components, self.ctx.cost_by_resource,
        ))
        return self.enhance_findings(findings, workspaces + components)
