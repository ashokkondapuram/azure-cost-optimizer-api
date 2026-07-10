"""Sub-engine — owned by network-firewall IT service."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.network_firewall.engine.analysis import analyze_firewalls


class FirewallSubEngine(ResourceSubEngine):
    component = 'Azure Firewall'
    bucket_keys = ('firewalls',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        resources = self.prepare_resources(buckets.get("firewalls") or [])
        findings = analyze_firewalls(self.engine, self.ctx.subscription_id, resources, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, resources)
