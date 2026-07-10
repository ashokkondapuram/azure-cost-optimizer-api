"""Sub-engine — owned by monitoring-appinsights IT service."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.monitoring_appinsights.engine.analysis import analyze_app_insights


class AppInsightsSubEngine(ResourceSubEngine):
    component = 'Application Insights'
    bucket_keys = ('app_insights_components',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        resources = self.prepare_resources(buckets.get("app_insights_components") or [])
        findings = analyze_app_insights(self.engine, self.ctx.subscription_id, resources, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, resources)
