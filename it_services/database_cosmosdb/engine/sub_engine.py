"""Cosmos DB optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.database_cosmosdb.engine.analysis import analyze_cosmos


class CosmosSubEngine(ResourceSubEngine):
    component = "Cosmos DB"
    bucket_keys = ('cosmosdb',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        accounts = self.prepare_resources(buckets.get("cosmosdb") or [])
        findings = analyze_cosmos(self.engine, self.ctx.subscription_id, accounts, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, accounts)
