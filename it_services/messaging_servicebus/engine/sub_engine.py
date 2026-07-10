"""Sub-engine — owned by messaging-servicebus IT service."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.messaging_servicebus.engine.analysis import analyze_service_bus


class ServiceBusSubEngine(ResourceSubEngine):
    component = 'Service Bus namespace'
    bucket_keys = ('service_bus_namespaces',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        resources = self.prepare_resources(buckets.get("service_bus_namespaces") or [])
        findings = analyze_service_bus(self.engine, self.ctx.subscription_id, resources, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, resources)
