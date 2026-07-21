"""Cosmos DB analysis configuration — cosmosdb-assessment.json is authoritative."""

from __future__ import annotations

from typing import Any

from it_services.database_cosmosdb.assessment_bridge import (
    cosmos_rule_ids,
    extended_cosmos_spec_payload,
    hydrate_cosmos_rules,
)

__all__ = [
    "cosmos_rule_ids",
    "extended_cosmos_spec_payload",
    "hydrate_cosmos_rules",
    "supplemental_cosmos_rules",
]


def supplemental_cosmos_rules() -> dict[str, Any]:
    """Cosmos DB rules are defined in cosmosdb-assessment.json and hydrated onto ADVANCED_RULES."""
    return {}
