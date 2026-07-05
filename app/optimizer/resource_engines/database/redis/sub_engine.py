"""Redis Cache optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.resource_engines.runtime.base import ResourceSubEngine
from app.optimizer.resource_engines.database.redis.analysis import analyze_redis


class RedisSubEngine(ResourceSubEngine):
    component = "Redis Cache"
    bucket_keys = ('redis_caches',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        caches = self.prepare_resources(buckets.get("redis_caches") or [])
        findings = analyze_redis(self.engine, self.ctx.subscription_id, caches, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, caches)
