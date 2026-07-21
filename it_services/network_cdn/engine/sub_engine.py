"""Sub-engine — owned by network-cdn IT service."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.network_cdn.engine.analysis import analyze_cdn_profiles


class CdnSubEngine(ResourceSubEngine):
    component = 'CDN profile'
    bucket_keys = ('cdn_profiles',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        resources = self.prepare_resources(buckets.get("cdn_profiles") or [])
        findings = analyze_cdn_profiles(self.engine, self.ctx.subscription_id, resources, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, resources)
