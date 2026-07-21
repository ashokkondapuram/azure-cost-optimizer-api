"""SQL Database optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.database_sql.engine.analysis import analyze_sql


class SqlSubEngine(ResourceSubEngine):
    component = "SQL Database"
    bucket_keys = ('sql_servers', 'sql_databases')

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        servers = self.prepare_resources(buckets.get("sql_servers") or [])
        databases = self.prepare_resources(buckets.get("sql_databases") or [])
        findings = analyze_sql(self.engine, self.ctx.subscription_id, databases, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, servers + databases)
