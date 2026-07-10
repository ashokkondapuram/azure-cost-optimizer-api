"""Network Security Groups optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.network_nsg.engine.analysis import analyze_nsgs


class NsgSubEngine(ResourceSubEngine):
    component = "Network Security Groups"
    bucket_keys = ('nsgs',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        nsgs = self.prepare_resources(buckets.get("nsgs") or [])
        findings = analyze_nsgs(self.engine, self.ctx.subscription_id, nsgs, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, nsgs)
