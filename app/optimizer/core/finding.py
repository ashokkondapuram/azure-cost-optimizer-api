"""Extended optimization finding model."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ExtendedFinding:
    rule_id: str
    rule_name: str
    category: str
    severity: str
    resource_id: str
    resource_name: str
    resource_type: str
    subscription_id: str
    resource_group: str
    location: str
    detail: str
    recommendation: str
    estimated_savings_usd: float
    annualized_savings_usd: float
    waste_score: int
    confidence_score: int
    action_priority: str
    impact: str
    evidence: dict[str, Any]
    tags: dict[str, Any]
    detected_at: str
    related_resource_ids: list[str] = field(default_factory=list)
    chain_id: str | None = None
    chain_step: int | None = None
    chain_total: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
