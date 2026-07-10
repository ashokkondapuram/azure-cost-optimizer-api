"""Sub-engine — owned by analytics-mlworkspace IT service."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.analytics_mlworkspace.engine.analysis import analyze_ml_workspaces


class MlWorkspaceSubEngine(ResourceSubEngine):
    component = 'Azure ML workspace'
    bucket_keys = ('ml_workspaces',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        resources = self.prepare_resources(buckets.get("ml_workspaces") or [])
        findings = analyze_ml_workspaces(self.engine, self.ctx.subscription_id, resources, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, resources)
