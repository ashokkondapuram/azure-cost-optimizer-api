"""Public IPs optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.network_publicip.engine.analysis import analyze_public_ips


class PublicIpSubEngine(ResourceSubEngine):
    component = "Public IPs"
    bucket_keys = ('public_ips',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        ips = self.prepare_resources(buckets.get("public_ips") or [])
        findings = analyze_public_ips(self.engine, self.ctx.subscription_id, ips, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, ips)
