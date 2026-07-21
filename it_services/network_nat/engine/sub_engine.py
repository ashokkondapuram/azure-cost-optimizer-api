"""NAT Gateways optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.network_nat.engine.analysis import analyze_nat_gateways


class NatSubEngine(ResourceSubEngine):
    component = "NAT Gateways"
    bucket_keys = ('nat_gateways',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        nats = self.prepare_resources(buckets.get("nat_gateways") or [])
        findings = analyze_nat_gateways(self.engine, self.ctx.subscription_id, nats, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, nats)
