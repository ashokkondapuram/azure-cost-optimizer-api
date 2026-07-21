"""Container Registry optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.containers_acr.engine.analysis import analyze_acr


class AcrSubEngine(ResourceSubEngine):
    component = "Container Registry"
    bucket_keys = ('container_registries',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        registries = self.prepare_resources(buckets.get("container_registries") or [])
        findings = analyze_acr(self.engine, self.ctx.subscription_id, registries, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, registries)
