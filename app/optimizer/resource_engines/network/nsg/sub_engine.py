"""Network Security Groups optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.resource_engines.runtime.base import ResourceSubEngine
from app.optimizer.resource_engines.network.nsg.analysis import analyze_nsgs


class NsgSubEngine(ResourceSubEngine):
    component = "Network Security Groups"
    bucket_keys = ('nsgs',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        nsgs = self.prepare_resources(buckets.get("nsgs") or [])
        findings = analyze_nsgs(self.engine, self.ctx.subscription_id, nsgs)
        return self.enhance_findings(findings, nsgs)
