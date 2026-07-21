"""Sub-engine — owned by analytics-synapse IT service."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.analytics_synapse.engine.analysis import analyze_synapse


class SynapseSubEngine(ResourceSubEngine):
    component = 'Azure Synapse'
    bucket_keys = ('synapse_workspaces',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        resources = self.prepare_resources(buckets.get("synapse_workspaces") or [])
        findings = analyze_synapse(self.engine, self.ctx.subscription_id, resources, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, resources)
