"""Sub-engine — owned by network-privatelinkservice IT service."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.network_privatelinkservice.engine.analysis import analyze_private_link_services


class PrivateLinkServiceSubEngine(ResourceSubEngine):
    component = 'Private link service'
    bucket_keys = ('private_link_services',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        resources = self.prepare_resources(buckets.get("private_link_services") or [])
        findings = analyze_private_link_services(self.engine, self.ctx.subscription_id, resources, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, resources)
