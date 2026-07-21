"""Sub-engine — owned by network-frontdoor IT service."""

from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.network_frontdoor.engine.analysis import analyze_front_doors


class FrontDoorSubEngine(ResourceSubEngine):
    component = "Azure Front Door"
    bucket_keys = ("front_doors",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        resources = self.prepare_resources(buckets.get("front_doors") or [])
        findings = analyze_front_doors(
            self.engine, self.ctx.subscription_id, resources, self.ctx.cost_by_resource,
        )
        return self.enhance_findings(findings, resources)
