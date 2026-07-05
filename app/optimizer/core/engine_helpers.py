"""Shared helper methods for extended optimization analysis."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.finding_evidence import enrich_evidence
from app.optimizer.advanced_rules import AdvancedRule
from app.optimizer.core.finding import ExtendedFinding
from app.optimizer.resource_engines.compute.vm.helpers import (
    emit_vm_sizing_finding,
    vm_catalog,
    vm_utilization,
)


class EngineAnalysisHelpers:
    """Mixin providing finding builders and metric helpers used by resource analyzers."""

    rules: dict[str, AdvancedRule]
    _vm_catalog_cache: dict[tuple[str, str], list[dict[str, Any]]]

    def _vm_catalog(self, subscription_id: str, location: str) -> list[dict[str, Any]]:
        return vm_catalog(self, subscription_id, location)

    def _vm_utilization(self, vm: dict, vm_metrics: dict[str, dict]):
        return vm_utilization(self, vm, vm_metrics)

    def _emit_vm_sizing_finding(self, **kwargs) -> ExtendedFinding | None:
        return emit_vm_sizing_finding(self, **kwargs)

    def _finding(
        self,
        *,
        rule: AdvancedRule,
        subscription_id: str,
        resource: dict,
        detail: str,
        recommendation: str,
        savings: float,
        waste_score: int,
        confidence: int,
        priority: str,
        impact: str,
        evidence: dict[str, Any],
        related_resource_ids: list[str] | None = None,
        chain_id: str | None = None,
        chain_step: int | None = None,
        chain_total: int | None = None,
    ) -> ExtendedFinding:
        rid = resource.get("id") or ""
        tech_facts = resource.get("_technical_facts") or {}
        resource_elements = resource.get("_resource_elements")
        merged_evidence = dict(tech_facts)
        merged_evidence.update(evidence)
        if resource_elements:
            merged_evidence["resource_elements"] = resource_elements
        return ExtendedFinding(
            rule_id=rule.id,
            rule_name=rule.name,
            category=rule.category.value,
            severity=rule.severity.value,
            resource_id=rid,
            resource_name=resource.get("name") or "",
            resource_type=resource.get("type") or "",
            subscription_id=subscription_id,
            resource_group=self._extract_rg(rid),
            location=resource.get("location") or "",
            detail=detail,
            recommendation=recommendation,
            estimated_savings_usd=round(savings, 2),
            annualized_savings_usd=round(savings * 12, 2),
            waste_score=waste_score,
            confidence_score=confidence,
            action_priority=priority,
            impact=impact,
            evidence=enrich_evidence(
                rule.id,
                merged_evidence,
                {
                    "rule_id": rule.id,
                    "resource_id": rid,
                    "resource_type": resource.get("type") or "",
                    "detail": detail,
                    "estimated_savings_usd": round(savings, 2),
                },
            ),
            tags=resource.get("tags") or {},
            detected_at=datetime.now(timezone.utc).isoformat(),
            related_resource_ids=list(related_resource_ids or []),
            chain_id=chain_id,
            chain_step=chain_step,
            chain_total=chain_total,
        )

    def _count_by(self, findings: list[ExtendedFinding], field: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in findings:
            key = getattr(f, field)
            out[key] = out.get(key, 0) + 1
        return out

    def _top_rules(self, findings: list[ExtendedFinding], limit: int = 5) -> list[dict[str, Any]]:
        totals: dict[str, dict[str, Any]] = {}
        for finding in findings:
            row = totals.setdefault(
                finding.rule_id,
                {
                    "rule_id": finding.rule_id,
                    "rule_name": finding.rule_name,
                    "count": 0,
                    "estimated_savings_usd": 0.0,
                },
            )
            row["count"] += 1
            row["estimated_savings_usd"] = round(
                row["estimated_savings_usd"] + finding.estimated_savings_usd, 2,
            )
        return sorted(
            totals.values(), key=lambda r: (-r["estimated_savings_usd"], -r["count"]),
        )[:limit]

    def _severity_rank(self, severity: str) -> int:
        return {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}.get(severity, 9)

    def _extract_rg(self, resource_id: str) -> str:
        parts = resource_id.split("/")
        for i, p in enumerate(parts):
            if p.lower() == "resourcegroups" and i + 1 < len(parts):
                return parts[i + 1]
        return ""

    def _metric_average(self, metrics: dict[str, Any] | None, name: str) -> float | None:
        if not metrics:
            return None
        for item in metrics.get("value", []):
            if (item.get("name") or {}).get("value") == name:
                vals = []
                for ts in item.get("timeseries", []):
                    for point in ts.get("data", []):
                        if point.get("average") is not None:
                            vals.append(point["average"])
                if vals:
                    return sum(vals) / len(vals)
        return None

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            return None

    def _budget_current_spend(self, props: dict[str, Any], fallback: float) -> float:
        current_spend = props.get("currentSpend") or {}
        if isinstance(current_spend, dict):
            return float(current_spend.get("amount") or fallback or 0)
        return float(current_spend or fallback or 0)

    def _budget_forecast_spend(self, props: dict[str, Any]) -> float:
        forecast = props.get("forecastSpend") or props.get("forecast")
        if isinstance(forecast, dict):
            return float(forecast.get("amount") or 0)
        return float(forecast or 0)

    def _generic_metric_average(self, metrics: dict[str, Any] | None) -> float | None:
        if not metrics:
            return None
        vals = []
        for item in metrics.get("value", []):
            for ts in item.get("timeseries", []):
                for point in ts.get("data", []):
                    if point.get("average") is not None:
                        vals.append(point["average"])
        if vals:
            return sum(vals) / len(vals)
        return None
