"""Standard optimization finding model (base engine tier)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.finding_evidence import build_rule_evidence
from app.optimizer.engine_filters import apply_waste_score_multiplier, effective_severity
from app.optimizer.rules import Rule


def extract_subscription_id(resource_id: str) -> str:
    parts = resource_id.lower().split("/")
    try:
        return parts[parts.index("subscriptions") + 1]
    except (ValueError, IndexError):
        return ""


def extract_resource_group(resource_id: str) -> str:
    parts = resource_id.lower().split("/")
    try:
        return parts[parts.index("resourcegroups") + 1]
    except (ValueError, IndexError):
        return ""


class Finding:
    __slots__ = (
        "rule_id", "rule_name", "category", "severity",
        "resource_id", "resource_name", "resource_type",
        "subscription_id", "resource_group", "location",
        "detail", "recommendation", "estimated_savings_usd",
        "waste_score", "tags", "detected_at", "evidence",
    )

    def __init__(
        self,
        rule: Rule,
        resource: dict,
        detail: str,
        recommendation: str,
        savings: float = 0.0,
        score: int = 50,
        evidence: dict[str, Any] | None = None,
        global_config: dict[str, Any] | None = None,
    ):
        self.rule_id = rule.id
        self.rule_name = rule.name
        self.category = rule.category.value
        self.severity = effective_severity(rule.severity.value, resource, global_config)
        self.resource_id = resource.get("id", "")
        self.resource_name = resource.get("name", "")
        self.resource_type = resource.get("type", "")
        self.subscription_id = extract_subscription_id(resource.get("id", ""))
        self.resource_group = extract_resource_group(resource.get("id", ""))
        self.location = resource.get("location", "")
        self.detail = detail
        self.recommendation = recommendation
        self.waste_score = apply_waste_score_multiplier(
            score, {"waste_score_multiplier": getattr(rule, "waste_score_multiplier", 1.0)},
        )
        self.tags = resource.get("tags") or {}
        self.detected_at = datetime.now(timezone.utc).isoformat()
        savings = round(savings, 2)
        self.estimated_savings_usd = savings
        self.evidence = build_rule_evidence(
            rule.id,
            evidence or {},
            finding={
                "rule_id": rule.id,
                "resource_id": resource.get("id", ""),
                "resource_type": resource.get("type", ""),
                "detail": detail,
                "estimated_savings_usd": savings,
            },
            estimated_savings_usd=savings,
        )

    def to_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}
