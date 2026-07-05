"""Shared analysis context passed to each resource sub-engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.optimizer.advanced_rules import AdvancedRule


@dataclass
class AnalysisContext:
    subscription_id: str
    rules: dict[str, AdvancedRule]
    cost_by_resource: dict[str, float] = field(default_factory=dict)
    vm_metrics: dict[str, dict] = field(default_factory=dict)
    node_metrics: dict[str, dict] = field(default_factory=dict)
    resource_metrics: dict[str, dict] = field(default_factory=dict)
    resource_facts: dict[str, dict[str, float]] = field(default_factory=dict)
    aks_node_pools: dict[str, list] = field(default_factory=dict)
    subscription_spend_usd: float = 0.0

    def metrics_for_resource(self, resource_id: str, *, kind: str | None = None) -> dict[str, Any] | None:
        rid = (resource_id or "").lower()
        if kind == "node":
            return self.node_metrics.get(rid)
        if kind == "vm":
            return self.vm_metrics.get(rid) or self.resource_metrics.get(rid)
        return self.resource_metrics.get(rid) or self.vm_metrics.get(rid)

    def facts_for_resource(self, resource_id: str) -> dict[str, float]:
        return dict(self.resource_facts.get((resource_id or "").lower(), {}))
