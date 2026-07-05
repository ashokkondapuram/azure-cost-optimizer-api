"""Managed Disks optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.resource_engines.runtime.base import ResourceSubEngine
from app.optimizer.resource_engines.compute.disk.analysis import analyze_disks


class DiskSubEngine(ResourceSubEngine):
    component = "Managed Disks"
    bucket_keys = ('disks',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        disks = self.prepare_resources(buckets.get("disks") or [])
        findings = analyze_disks(self.engine, self.ctx.subscription_id, disks, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, disks)
