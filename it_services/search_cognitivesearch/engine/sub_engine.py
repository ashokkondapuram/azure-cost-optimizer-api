"""Search optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.search_cognitivesearch.engine.analysis import analyze_cognitive_search


class SearchSubEngine(ResourceSubEngine):
    component = "Search"
    bucket_keys = ("cognitive_search_services",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        services = self.prepare_resources(buckets.get("cognitive_search_services") or [])
        findings = analyze_cognitive_search(
            self.engine, self.ctx.subscription_id, services, self.ctx.cost_by_resource,
        )
        return self.enhance_findings(findings, services)
