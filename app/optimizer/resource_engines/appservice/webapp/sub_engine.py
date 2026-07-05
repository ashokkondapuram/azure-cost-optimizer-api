"""App Service optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.resource_engines.runtime.base import ResourceSubEngine
from app.optimizer.resource_engines.appservice.webapp.analysis import analyze_app_services


class AppServiceSubEngine(ResourceSubEngine):
    component = "App Service"
    bucket_keys = ('app_services', 'app_service_plans')

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        apps = self.prepare_resources(buckets.get("app_services") or [])
        plans = self.prepare_resources(buckets.get("app_service_plans") or [])
        findings = analyze_app_services(self.engine, self.ctx.subscription_id, apps, plans, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, apps + plans)
