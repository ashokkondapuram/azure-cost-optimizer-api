"""Disk Snapshots optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.compute_snapshot.engine.analysis import analyze_snapshots


class SnapshotSubEngine(ResourceSubEngine):
    component = "Disk Snapshots"
    bucket_keys = ('snapshots',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        snapshots = self.prepare_resources(buckets.get("snapshots") or [])
        findings = analyze_snapshots(self.engine, self.ctx.subscription_id, snapshots, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, snapshots)
