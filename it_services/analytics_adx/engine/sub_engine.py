"""Sub-engine — owned by analytics-adx IT service."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.analytics_adx.engine.analysis import analyze_adx


class AdxSubEngine(ResourceSubEngine):
    component = 'Azure Data Explorer'
    bucket_keys = ('adx_clusters',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        resources = self.prepare_resources(buckets.get("adx_clusters") or [])
        findings = analyze_adx(self.engine, self.ctx.subscription_id, resources, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, resources)
