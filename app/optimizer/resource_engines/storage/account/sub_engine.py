"""Storage Accounts optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.resource_engines.runtime.base import ResourceSubEngine
from app.optimizer.resource_engines.storage.account.analysis import analyze_storage


class StorageSubEngine(ResourceSubEngine):
    component = "Storage Accounts"
    bucket_keys = ('storage',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        storage = self.prepare_resources(buckets.get("storage") or [])
        findings = analyze_storage(self.engine, self.ctx.subscription_id, storage, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, storage)
