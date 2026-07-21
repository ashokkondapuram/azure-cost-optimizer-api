"""Sub-engine — owned by integration-datafactory IT service."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.integration_datafactory.engine.analysis import analyze_data_factories


class DataFactorySubEngine(ResourceSubEngine):
    component = 'Data Factory'
    bucket_keys = ('data_factories',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        resources = self.prepare_resources(buckets.get("data_factories") or [])
        findings = analyze_data_factories(self.engine, self.ctx.subscription_id, resources, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, resources)
