"""Central registry of all optimization rule IDs across engine tiers."""
from __future__ import annotations

from app.cost_export_recommendations import COST_EXPORT_RULES
from app.optimizer.advanced_rules import ADVANCED_RULES
from app.optimizer.rule_catalog import RULE_ALIASES
from app.optimizer.rules import DEFAULT_RULES

COST_EXPORT_RULE_IDS: frozenset[str] = frozenset(r.id for r in COST_EXPORT_RULES)
STANDARD_RULE_IDS: frozenset[str] = frozenset(DEFAULT_RULES)
EXTENDED_RULE_IDS: frozenset[str] = frozenset(ADVANCED_RULES)
RULE_ALIAS_IDS: frozenset[str] = frozenset(RULE_ALIASES)
_ENGINE_RULE_IDS: frozenset[str] = (
    STANDARD_RULE_IDS | EXTENDED_RULE_IDS | COST_EXPORT_RULE_IDS | RULE_ALIAS_IDS
)

_ASSESSMENT_RULE_IDS: frozenset[str] | None = None


def _assessment_rule_ids() -> frozenset[str]:
    global _ASSESSMENT_RULE_IDS
    if _ASSESSMENT_RULE_IDS is None:
        from app.assessment.catalog import collect_assessment_rule_ids

        _ASSESSMENT_RULE_IDS = frozenset(collect_assessment_rule_ids())
    return _ASSESSMENT_RULE_IDS


ALL_KNOWN_RULE_IDS: frozenset[str] = _ENGINE_RULE_IDS


def all_known_rule_ids() -> frozenset[str]:
    """Engine, cost-export, alias, and assessment JSON rule identifiers."""
    return _ENGINE_RULE_IDS | _assessment_rule_ids()


def is_known_rule(rule_id: str) -> bool:
    rid = (rule_id or "").strip()
    if not rid:
        return False
    if rid.startswith("advisor_"):
        return True
    return rid in _ENGINE_RULE_IDS or rid in _assessment_rule_ids()


def rule_engine_tier(rule_id: str) -> str | None:
    from app.optimizer.rule_catalog import resolve_rule_id

    canonical = resolve_rule_id(rule_id)
    if canonical in COST_EXPORT_RULE_IDS:
        return "cost_export"
    if canonical in EXTENDED_RULE_IDS:
        return "extended"
    if canonical in STANDARD_RULE_IDS:
        return "standard"
    if rule_id in RULE_ALIAS_IDS:
        return rule_engine_tier(canonical)
    return None
