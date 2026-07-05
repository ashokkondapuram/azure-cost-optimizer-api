"""PostgreSQL optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.resource_engines.runtime.base import ResourceSubEngine
from app.optimizer.resource_engines.database.postgresql.analysis import analyze_postgresql


class PostgresqlSubEngine(ResourceSubEngine):
    component = "PostgreSQL"
    bucket_keys = ('postgresql',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        servers = self.prepare_resources(buckets.get("postgresql") or [])
        findings = analyze_postgresql(self.engine, self.ctx.subscription_id, servers, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, servers)
