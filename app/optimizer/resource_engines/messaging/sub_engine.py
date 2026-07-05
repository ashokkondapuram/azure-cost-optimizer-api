"""Messaging optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.resource_engines.runtime.base import ResourceSubEngine
from app.optimizer.resource_engines.messaging.analysis import analyze_event_hubs, analyze_service_bus


class MessagingSubEngine(ResourceSubEngine):
    component = "Messaging"
    bucket_keys = ("event_hubs", "service_bus_namespaces")

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        event_hubs = self.prepare_resources(buckets.get("event_hubs") or [])
        service_bus = self.prepare_resources(buckets.get("service_bus_namespaces") or [])
        findings = analyze_event_hubs(self.engine, self.ctx.subscription_id, event_hubs, self.ctx.cost_by_resource)
        findings.extend(analyze_service_bus(self.engine, self.ctx.subscription_id, service_bus, self.ctx.cost_by_resource))
        return self.enhance_findings(findings, event_hubs + service_bus)
