"""Sub-engine — owned by integration-apim IT service."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.integration_apim.engine.analysis import analyze_apim


class ApimSubEngine(ResourceSubEngine):
    component = 'API Management'
    bucket_keys = ('apim_services',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        resources = self.prepare_resources(buckets.get("apim_services") or [])
        findings = analyze_apim(self.engine, self.ctx.subscription_id, resources, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, resources)
