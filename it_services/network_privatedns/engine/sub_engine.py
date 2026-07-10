"""Sub-engine — owned by network-privatedns IT service."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.network_privatedns.engine.analysis import analyze_private_dns_zones


class PrivateDnsSubEngine(ResourceSubEngine):
    component = 'Private DNS zone'
    bucket_keys = ('private_dns_zones',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        resources = self.prepare_resources(buckets.get("private_dns_zones") or [])
        findings = analyze_private_dns_zones(self.engine, self.ctx.subscription_id, resources, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, resources)
