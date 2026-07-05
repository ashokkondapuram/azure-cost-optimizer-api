"""Commitments optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.resource_engines.runtime.base import ResourceSubEngine
from app.optimizer.resource_engines.cost.commitments.analysis import analyze_commitments


class CommitmentsSubEngine(ResourceSubEngine):
    component = "Commitments"
    bucket_keys = ("vms",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        vms = self.prepare_resources(buckets.get("vms") or [], metrics_kind="vm")
        findings = analyze_commitments(
            self.engine,
            self.ctx.subscription_id,
            vms,
            self.ctx.cost_by_resource,
            self.ctx.subscription_spend_usd,
            resource_cost_histories=self.ctx.resource_cost_histories,
        )
        return self.enhance_findings(findings, vms)
