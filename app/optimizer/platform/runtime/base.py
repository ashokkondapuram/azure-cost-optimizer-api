"""Base class for per-resource optimization sub-engines."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.assessment.advisor_bridge import (
    advisor_rows_to_findings,
    filter_duplicate_advisor_findings,
)
from app.assessment.bridge import assessment_dict_to_extended_finding, resource_to_assessment_record
from app.assessment.catalog import get_assessment_for_arm_type
from app.assessment.runtime import evaluate_assessment_rules, rule_to_finding
from app.optimizer.engine_filters import should_skip_resource
from .context import AnalysisContext
from .envelope import build_resource_envelope, merge_envelope_into_evidence


class ResourceSubEngine(ABC):
    """Analyzes one Azure component using assessment JSON rules and Python analyzers."""

    component: str
    bucket_keys: tuple[str, ...]

    def __init__(self, engine: Any, ctx: AnalysisContext):
        self.engine = engine
        self.ctx = ctx

    @abstractmethod
    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        raise NotImplementedError

    def evaluate_assessment_findings(self, resources: list[dict]) -> list[Any]:
        """Evaluate data/*-assessment.json rules for prepared inventory resources."""
        findings: list[Any] = []
        seen_keys: set[tuple[str, str]] = set()

        for resource in resources:
            record = resource_to_assessment_record(resource, self.ctx)
            arm_type = record.get("resource_type") or ""
            assessment = get_assessment_for_arm_type(arm_type)
            if not assessment:
                continue

            schema = str(assessment.get("schema_version") or assessment.get("schemaVersion") or "")
            if schema.startswith("2"):
                # v2 assessments use Python engine rules[] only — skip legacy JSON governance rules.
                continue

            matched = evaluate_assessment_rules(
                assessment,
                record,
                include_assessment_rules=True,
                include_recommendation_rules=True,
                include_best_optimization_rules=False,
                exclude_investigate=True,
                exclude_metric_gaps=True,
            )
            for rule in matched:
                rule_id = rule.get("id") or ""
                key = ((record.get("resource_id") or "").lower(), rule_id)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                finding_dict = rule_to_finding(
                    rule,
                    resource=record,
                    assessment_file=assessment.get("_file"),
                    assessment=assessment,
                )
                findings.append(
                    assessment_dict_to_extended_finding(
                        finding_dict,
                        subscription_id=self.ctx.subscription_id,
                        resource=resource,
                    )
                )

            advisor_rows = self.ctx.advisor_for_resource(record.get("resource_id") or "")
            if advisor_rows:
                advisor_dicts = advisor_rows_to_findings(
                    advisor_rows,
                    resource=record,
                    subscription_id=self.ctx.subscription_id,
                )
                json_dicts = [
                    {
                        "rule_id": f.rule_id,
                        "category": f.category,
                        "evidence": f.evidence,
                    }
                    for f in findings
                    if (f.resource_id or "").lower() == (record.get("resource_id") or "").lower()
                ]
                for advisor_dict in filter_duplicate_advisor_findings(json_dicts, advisor_dicts):
                    adv_key = (
                        (advisor_dict.get("resource_id") or "").lower(),
                        advisor_dict.get("rule_id") or "",
                    )
                    if adv_key in seen_keys:
                        continue
                    seen_keys.add(adv_key)
                    findings.append(
                        assessment_dict_to_extended_finding(
                            advisor_dict,
                            subscription_id=self.ctx.subscription_id,
                            resource=resource,
                        )
                    )
        return findings

    def prepare_resources(
        self,
        resources: list[dict],
        *,
        metrics_kind: str | None = None,
    ) -> list[dict]:
        """Enrich resources with technical facts from sync specs before rule checks."""
        prepared: list[dict] = []
        for resource in resources:
            if should_skip_resource(resource, self.ctx.global_config):
                continue
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
