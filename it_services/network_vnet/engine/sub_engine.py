"""Sub-engine — owned by network-vnet IT service."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.network_vnet.engine.analysis import analyze_vnets


class VnetSubEngine(ResourceSubEngine):
    component = 'Virtual network'
    bucket_keys = ('vnets',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        resources = self.prepare_resources(buckets.get("vnets") or [])
        findings = analyze_vnets(self.engine, self.ctx.subscription_id, resources, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, resources)
