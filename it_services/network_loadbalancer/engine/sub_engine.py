"""Load Balancers optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.network_loadbalancer.engine.analysis import analyze_load_balancers


class LoadBalancerSubEngine(ResourceSubEngine):
    component = "Load Balancers"
    bucket_keys = ('load_balancers',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        lbs = self.prepare_resources(buckets.get("load_balancers") or [])
        findings = analyze_load_balancers(self.engine, self.ctx.subscription_id, lbs, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, lbs)
