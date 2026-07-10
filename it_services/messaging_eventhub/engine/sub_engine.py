"""Sub-engine — owned by messaging-eventhub IT service."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.messaging_eventhub.engine.analysis import analyze_event_hubs


class EventHubSubEngine(ResourceSubEngine):
    component = 'Event Hubs namespace'
    bucket_keys = ('event_hubs',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        resources = self.prepare_resources(buckets.get("event_hubs") or [])
        findings = analyze_event_hubs(self.engine, self.ctx.subscription_id, resources, self.ctx.cost_by_resource)
        return self.enhance_findings(findings, resources)
