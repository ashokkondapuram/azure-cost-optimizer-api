"""AKS optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.containers_aks.engine.analysis import analyze_aks


class AksSubEngine(ResourceSubEngine):
    component = "AKS"
    bucket_keys = ('aks_clusters',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        clusters = self.prepare_resources(buckets.get("aks_clusters") or [], metrics_kind="node")
        findings = analyze_aks(self.engine, self.ctx.subscription_id, clusters, self.ctx.aks_node_pools, self.ctx.node_metrics, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, clusters)
