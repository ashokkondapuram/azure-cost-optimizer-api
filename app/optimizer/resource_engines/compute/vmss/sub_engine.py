"""Virtual Machine Scale Sets optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.resource_engines.runtime.base import ResourceSubEngine
from app.optimizer.resource_engines.compute.vm.analysis import analyze_vms
from app.optimizer.resource_engines.compute.vmss.analysis import analyze_vmss


class VmssSubEngine(ResourceSubEngine):
    component = "Virtual Machine Scale Sets"
    bucket_keys = ('vmss',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        scale_sets = self.prepare_resources(buckets.get("vmss") or [], metrics_kind="vm")
        findings = analyze_vms(
            self.engine,
            self.ctx.subscription_id,
            scale_sets,
            self.ctx.vm_metrics,
            self.ctx.cost_by_resource,
            subscription_spend_usd=self.ctx.subscription_spend_usd,
        )
        findings.extend(analyze_vmss(
            self.engine,
            self.ctx.subscription_id,
            scale_sets,
            self.ctx.vm_metrics,
            self.ctx.cost_by_resource,
        ))
        return self.enhance_findings(findings, scale_sets)
