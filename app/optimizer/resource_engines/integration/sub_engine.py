"""Integration optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.resource_engines.runtime.base import ResourceSubEngine
from app.optimizer.resource_engines.integration.analysis import (
    analyze_apim,
    analyze_data_factories,
    analyze_logic_apps,
)


class IntegrationSubEngine(ResourceSubEngine):
    component = "Integration"
    bucket_keys = ("apim_services", "data_factories", "logic_apps")

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        apim = self.prepare_resources(buckets.get("apim_services") or [])
        factories = self.prepare_resources(buckets.get("data_factories") or [])
        workflows = self.prepare_resources(buckets.get("logic_apps") or [])
        findings = analyze_apim(self.engine, self.ctx.subscription_id, apim, self.ctx.cost_by_resource)
        findings.extend(analyze_data_factories(self.engine, self.ctx.subscription_id, factories, self.ctx.cost_by_resource))
        findings.extend(analyze_logic_apps(self.engine, self.ctx.subscription_id, workflows, self.ctx.cost_by_resource))
        return self.enhance_findings(findings, apim + factories + workflows)
