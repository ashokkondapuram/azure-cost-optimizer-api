"""Sub-engine — owned by integration-logicapp IT service."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.integration_logicapp.engine.analysis import analyze_logic_apps


class LogicAppSubEngine(ResourceSubEngine):
    component = 'Logic App'
    bucket_keys = ('logic_apps',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        resources = self.prepare_resources(buckets.get("logic_apps") or [])
        findings = analyze_logic_apps(self.engine, self.ctx.subscription_id, resources, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, resources)
