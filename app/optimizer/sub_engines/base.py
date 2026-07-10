"""Base class for per-resource optimization sub-engines."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .context import AnalysisContext
from .envelope import build_resource_envelope, merge_envelope_into_evidence


class ResourceSubEngine(ABC):
    """Analyzes one Azure component using the full synced resource envelope."""

    component: str
    bucket_keys: tuple[str, ...]

    def __init__(self, engine: Any, ctx: AnalysisContext):
        self.engine = engine
        self.ctx = ctx

    @abstractmethod
    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        raise NotImplementedError

    def prepare_resources(
        self,
        resources: list[dict],
        *,
        metrics_kind: str | None = None,
    ) -> list[dict]:
        """Enrich resources with technical facts from sync specs before rule checks."""
        prepared: list[dict] = []
        for resource in resources:
            rid = resource.get("id") or ""
            metrics = self.ctx.metrics_for_resource(rid, kind=metrics_kind)
            envelope = build_resource_envelope(resource, self.ctx, metrics=metrics)
            prepared.append(envelope.inject_into(resource))
        return prepared

    def enhance_findings(
        self,
        findings: list[Any],
        resources: list[dict],
    ) -> list[Any]:
        by_id = {(r.get("id") or "").lower(): r for r in resources}
        for finding in findings:
            rid = (finding.resource_id or "").lower()
            resource = by_id.get(rid, {})
            metrics = self.ctx.metrics_for_resource(rid)
            envelope = build_resource_envelope(resource, self.ctx, metrics=metrics)
            finding.evidence = merge_envelope_into_evidence(finding.evidence, envelope)
        return findings

    def _metrics_kind_for_resource(self, resource: dict[str, Any]) -> str | None:
        canonical = resource.get("_canonical_type") or ""
        if canonical == "compute/vm":
            return "vm"
        if canonical == "containers/aks":
            return "node"
        return None
