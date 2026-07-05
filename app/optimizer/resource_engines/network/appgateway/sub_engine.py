"""Application Gateways optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.resource_engines.runtime.base import ResourceSubEngine
from app.optimizer.resource_engines.network.appgateway.analysis import analyze_app_gateways


class AppGatewaySubEngine(ResourceSubEngine):
    component = "Application Gateways"
    bucket_keys = ('app_gateways',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        gateways = self.prepare_resources(buckets.get("app_gateways") or [])
        findings = analyze_app_gateways(self.engine, self.ctx.subscription_id, gateways, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, gateways)
