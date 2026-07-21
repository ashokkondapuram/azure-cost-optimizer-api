"""Network Interfaces optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.network_nic.engine.analysis import analyze_network_interfaces


class NicSubEngine(ResourceSubEngine):
    component = "Network Interfaces"
    bucket_keys = ('network_interfaces',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        nics = self.prepare_resources(buckets.get("network_interfaces") or [])
        findings = analyze_network_interfaces(self.engine, self.ctx.subscription_id, nics)
        return self.enhance_findings(findings, nics)
