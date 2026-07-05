"""Virtual Machines optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.resource_engines.runtime.base import ResourceSubEngine
from app.optimizer.resource_engines.compute.vm.analysis import analyze_vms


class VmSubEngine(ResourceSubEngine):
    component = "Virtual Machines"
    bucket_keys = ('vms',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        vms = self.prepare_resources(buckets.get("vms") or [], metrics_kind="vm")
        findings = analyze_vms(
            self.engine,
            self.ctx.subscription_id,
            vms,
            self.ctx.vm_metrics,
            self.ctx.cost_by_resource,
            subscription_spend_usd=self.ctx.subscription_spend_usd,
            resource_graph=self.ctx.resource_graph,
            resource_facts=self.ctx.resource_facts,
            resource_cost_histories=self.ctx.resource_cost_histories,
            utilization_trends=self.ctx.utilization_trends,
            workload_classes=self.ctx.workload_classes,
        )
        return self.enhance_findings(findings, vms)
