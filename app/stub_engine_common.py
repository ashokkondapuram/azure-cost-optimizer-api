"""Shared helpers for stub resource optimization engines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.cost_utils import savings_from_factor
from app.resource_utilization import confidence_with_monitor, structured_evidence


@dataclass(frozen=True)
class StubFindingDraft:
    rule_id: str
    detail: str
    recommendation: str
    savings: float
    waste_score: int
    confidence: int
    priority: str
    impact: str
    evidence: dict[str, Any]


def append_stub_draft(
    out: list,
    engine: Any,
    subscription_id: str,
    resource: dict[str, Any],
    rule: Any,
    draft: StubFindingDraft | None,
) -> None:
    if draft is None or not rule or not rule.enabled:
        return
    out.append(engine._finding(
        rule=rule,
        subscription_id=subscription_id,
        resource=resource,
        detail=draft.detail,
        recommendation=draft.recommendation,
        savings=draft.savings,
        waste_score=draft.waste_score,
        confidence=draft.confidence,
        priority=draft.priority,
        impact=draft.impact,
        evidence=draft.evidence,
    ))


def cost_savings(monthly: float, factor: float, *, min_savings: float = 0.0) -> float:
    savings = savings_from_factor(monthly, factor) if monthly > 0 else 0.0
    if min_savings > 0 and 0 < savings < min_savings:
        return 0.0
    return savings


def env_tag(resource: dict[str, Any]) -> str:
    tags = resource.get("tags") or {}
    return str(tags.get("environment") or tags.get("env") or "").lower()


def cost_finding_draft(
    *,
    rule_id: str,
    resource: dict[str, Any],
    monthly: float,
    detail_suffix: str,
    recommendation: str,
    savings_factor: float,
    waste_score: int,
    priority: str,
    impact: str,
    min_savings: float = 0.0,
    extra_evidence: dict[str, Any] | None = None,
) -> StubFindingDraft:
    name = resource.get("name") or ""
    evidence = {"monthly_cost_usd": monthly, **(extra_evidence or {})}
    return StubFindingDraft(
        rule_id=rule_id,
        detail=f"'{name}' has MTD spend of ${monthly:,.2f}. {detail_suffix}",
        recommendation=recommendation,
        savings=cost_savings(monthly, savings_factor, min_savings=min_savings),
        waste_score=waste_score,
        confidence=68,
        priority=priority,
        impact=impact,
        evidence=evidence,
    )


def metric_finding_draft(
    *,
    rule_id: str,
    resource: dict[str, Any],
    monthly: float,
    detail: str,
    recommendation: str,
    savings: float,
    waste_score: int,
    priority: str,
    impact: str,
    determination: str,
    summary: str,
    checks: list | None = None,
    extra: dict[str, Any] | None = None,
    required_keys: tuple[str, ...] = (),
) -> StubFindingDraft:
    return StubFindingDraft(
        rule_id=rule_id,
        detail=detail,
        recommendation=recommendation,
        savings=savings,
        waste_score=waste_score,
        confidence=confidence_with_monitor(70, resource, required_keys=required_keys),
        priority=priority,
        impact=impact,
        evidence=structured_evidence(
            resource,
            determination=determination,
            summary=summary,
            checks=checks or [],
            extra={"monthly_cost_usd": monthly, **(extra or {})},
        ),
    )
