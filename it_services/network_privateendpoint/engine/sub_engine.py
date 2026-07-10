"""Sub-engine — owned by network-privateendpoint IT service."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.network_privateendpoint.engine.analysis import analyze_private_endpoints


class PrivateEndpointSubEngine(ResourceSubEngine):
    component = 'Private endpoint'
    bucket_keys = ('private_endpoints',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        resources = self.prepare_resources(buckets.get("private_endpoints") or [])
        findings = analyze_private_endpoints(self.engine, self.ctx.subscription_id, resources, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, resources)
