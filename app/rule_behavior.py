"""Central rule behavior metadata — waste heatmap, hub savings, scoring, and actions.

New optimization rules are classified here via explicit overrides plus ID-pattern
inference. Hub, heatmap, scoring, and action synthesis should import from this module
instead of maintaining separate hardcoded rule-id frozensets.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.savings_aggregation import SavingsActionClass

# ── Scoring action types (consumed by advanced_engine + decision_engine) ────────

SCORING_DECOMMISSION = "decommission"
SCORING_RESIZE_DOWN = "resize_down"
SCORING_DOWNGRADE_DISK = "downgrade_disk"
SCORING_BUY_RESERVATION = "buy_reservation"
SCORING_INVESTIGATE = "investigate"
SCORING_MANUAL_REVIEW = "manual_review"

_SCORING_PRIORITY = (
    SCORING_MANUAL_REVIEW,
    SCORING_DECOMMISSION,
    SCORING_BUY_RESERVATION,
    SCORING_RESIZE_DOWN,
    SCORING_DOWNGRADE_DISK,
    SCORING_INVESTIGATE,
)

# ── Pattern tokens ────────────────────────────────────────────────────────────

_EXCLUDED_WASTE_TOKENS = (
    "BUDGET_",
    "RESERVED_",
    "SAVINGS_PLAN",
    "SPOT_OPPORTUNITY",
    "NO_RESERVED",
    "COMMITMENT_CANDIDATE",
    "GOVERNANCE_TAGS",
    "MISSING_GOVERNANCE",
)

_PERFORMANCE_TOKENS = (
    "SNAT_EXHAUSTION",
    "SNAT_PRESSURE",
    "NAT_PORT_PRESSURE",
    "MEMORY_PRESSURE",
    "QUEUE_DEPTH",
    "BOTTLENECK",
    "CU_SATURATION",
    "FAILED_EXTENDED",
    "PERMISSIVE",
    "THROTTLING",
    "UNDERPROVISIONED",
)

_MIGRATION_TOKENS = (
    "BASIC_SKU_MIGRATION",
    "SKU_V2_UPGRADE",
    "V2_UPGRADE",
)

_COMMITMENT_TOKENS = (
    "NO_RESERVED",
    "COMMITMENT_CANDIDATE",
    "RESERVED_OPPORTUNITY",
    "SAVINGS_PLAN_OPPORTUNITY",
    "SPOT_OPPORTUNITY",
)

_RELIABILITY_TOKENS = (
    "RELIABILITY",
    "HA_REQUIRED",
    "PROTECTION_EXTENDED",
    "HEALTH_EXTENDED",
    "VERSION_OUTDATED",
    "FAILED_EXTENDED",
)

_GOVERNANCE_TOKENS = (
    "GOVERNANCE_TAGS",
    "MISSING_GOVERNANCE",
    "PERMISSIVE",
)

_SCHEDULE_TOKENS = (
    "SCHEDULE_CANDIDATE",
    "NONPROD_SCHEDULING",
)

_DECOMMISSION_TOKENS = (
    "_IDLE",
    "IDLE_",
    "UNUSED",
    "UNATTACHED",
    "ORPHANED",
    "ORPHAN_",
    "STOPPED_BILLING",
    "STOPPED_EXTENDED",
    "WEBAPP_STOPPED",
    "ZOMBIE",
    "NO_BACKEND",
    "UNASSOCIATED",
    "EMPTY_POOL",
    "SNAPSHOT_ARCHIVE",
    "SNAPSHOT_STALE",
    "SNAPSHOT_OLD",
    "SNAPSHOT_RETENTION",
    "APP_IDLE",
    "DEALLOCATED",
)

_RIGHTSIZE_TOKENS = (
    "RIGHTSIZE",
    "SKU_SIZING",
    "DOWNSIZE",
    "AUTOSCALE_TUNING",
    "CONSOLIDATION",
    "CAPACITY_RIGHTSIZE",
    "COOL_TIER",
    "POD_DENSITY",
    "EGRESS_HIGH",
    "FLOW_LOG_COST",
    "IMAGE_RETENTION",
    "LOAD_LOW",
    "THROUGHPUT_RIGHTSIZE",
    "SUBNET_CONSOLIDATION",
    "UNDERUTILIZED",
    "OVERSIZE",
    "OVERSIZED",
    "TIER_REVIEW",
    "STORAGE_EXTENDED",
    "HA_UNNECESSARY",
    "SERVERLESS",
    "AUTOSCALE_EXTENDED",
)

_DISK_RIGHTSIZE_TOKENS = (
    "DISK_OVERSIZE",
    "DISK_CAPACITY",
    "DISK_UNUSED",
)

_DATABASE_WASTE_RULE_IDS = frozenset({
    "REDIS_IDLE_DETECTION",
    "REDIS_LOW_UTILIZATION",
    "REDIS_OVERSIZED",
    "REDIS_CLUSTER_UNNECESSARY",
    "POSTGRESQL_STOPPED_EXTENDED",
    "POSTGRESQL_LOW_COMPUTE_UTILIZATION",
})


@dataclass(frozen=True)
class RuleBehavior:
    action_class: str
    waste_heatmap: bool
    scoring_action: str | None = None


def canonical_rule_id(rule_id: str | None) -> str:
    rid = (rule_id or "").strip()
    if not rid:
        return ""
    try:
        from app.optimizer.rule_catalog import resolve_rule_id

        return resolve_rule_id(rid)
    except Exception:
        return rid


def _matches_any(rid: str, tokens: tuple[str, ...]) -> bool:
    return any(token in rid for token in tokens)


def _action_class(name: str) -> SavingsActionClass:
    from app.savings_aggregation import SavingsActionClass

    return SavingsActionClass(name)


def _infer_behavior(rule_id: str) -> RuleBehavior | None:
    rid = canonical_rule_id(rule_id).upper()
    if not rid:
        return None
    if any(token in rid for token in _EXCLUDED_WASTE_TOKENS):
        return RuleBehavior(_action_class("non_cost").value, False, SCORING_INVESTIGATE)

    if rid in _DATABASE_WASTE_RULE_IDS:
        if "IDLE" in rid or "STOPPED" in rid:
            return RuleBehavior(_action_class("decommission").value, True, SCORING_DECOMMISSION)
        return RuleBehavior(_action_class("rightsize").value, True, SCORING_RESIZE_DOWN)

    if _matches_any(rid, _PERFORMANCE_TOKENS):
        return RuleBehavior(_action_class("non_cost").value, False, SCORING_MANUAL_REVIEW)
    if _matches_any(rid, _MIGRATION_TOKENS):
        return RuleBehavior(_action_class("non_cost").value, False, SCORING_INVESTIGATE)
    if _matches_any(rid, _COMMITMENT_TOKENS):
        return RuleBehavior(_action_class("commitment").value, False, SCORING_BUY_RESERVATION)
    if _matches_any(rid, _GOVERNANCE_TOKENS):
        return RuleBehavior(_action_class("governance").value, False, SCORING_INVESTIGATE)
    if _matches_any(rid, _RELIABILITY_TOKENS):
        return RuleBehavior(_action_class("non_cost").value, False, SCORING_MANUAL_REVIEW)
    if _matches_any(rid, _SCHEDULE_TOKENS):
        return RuleBehavior(_action_class("schedule").value, False, SCORING_INVESTIGATE)

    if _matches_any(rid, _DECOMMISSION_TOKENS):
        return RuleBehavior(_action_class("decommission").value, True, SCORING_DECOMMISSION)

    if _matches_any(rid, _RIGHTSIZE_TOKENS):
        scoring = SCORING_DOWNGRADE_DISK if _matches_any(rid, _DISK_RIGHTSIZE_TOKENS) else SCORING_RESIZE_DOWN
        return RuleBehavior(_action_class("rightsize").value, False, scoring)

    return None


@lru_cache(maxsize=1)
def _explicit_overrides() -> dict[str, RuleBehavior]:
    """Rules where pattern inference would be wrong."""
    dec = _action_class("decommission").value
    rs = _action_class("rightsize").value
    nc = _action_class("non_cost").value
    oc = _action_class("other_cost").value
    return {
        "VM_MEMORY_PRESSURE_EXTENDED": RuleBehavior(nc, False, SCORING_MANUAL_REVIEW),
        "DISK_QUEUE_DEPTH_EXTENDED": RuleBehavior(nc, False, SCORING_MANUAL_REVIEW),
        "AKS_NODE_MEMORY_PRESSURE_EXTENDED": RuleBehavior(nc, False, SCORING_MANUAL_REVIEW),
        "LOAD_BALANCER_SNAT_PRESSURE": RuleBehavior(nc, False, SCORING_MANUAL_REVIEW),
        "NAT_GATEWAY_SNAT_EXHAUSTION": RuleBehavior(nc, False, SCORING_MANUAL_REVIEW),
        "APP_GATEWAY_CU_SATURATION": RuleBehavior(nc, False, SCORING_MANUAL_REVIEW),
        "PRIVATE_LINK_NAT_PORT_PRESSURE": RuleBehavior(nc, False, SCORING_MANUAL_REVIEW),
        "PRIVATE_ENDPOINT_FAILED_EXTENDED": RuleBehavior(nc, False, SCORING_MANUAL_REVIEW),
        "NSG_PERMISSIVE_EXTENDED": RuleBehavior(nc, False, SCORING_MANUAL_REVIEW),
        "NAT_GATEWAY_SKU_V2_UPGRADE": RuleBehavior(rs, False, SCORING_INVESTIGATE),
        "PUBLIC_IP_BASIC_SKU_MIGRATION": RuleBehavior(nc, False, SCORING_INVESTIGATE),
        "LOAD_BALANCER_BASIC_SKU_MIGRATION": RuleBehavior(nc, False, SCORING_INVESTIGATE),
        "VNET_UNUSED_SUBNET_EXTENDED": RuleBehavior(oc, False, SCORING_INVESTIGATE),
        "PRIVATE_ENDPOINT_UNDERUTILIZED": RuleBehavior(dec, False, SCORING_DECOMMISSION),
        "PRIVATE_DNS_UNUSED_ZONE": RuleBehavior(dec, False, SCORING_DECOMMISSION),
        "NSG_FLOW_LOG_COST": RuleBehavior(rs, False, SCORING_INVESTIGATE),
        "COST_HIGH_SPEND_REVIEW": RuleBehavior(oc, False, SCORING_INVESTIGATE),
    }


def _fallback_from_advanced_rule(rule_id: str) -> RuleBehavior | None:
    from app.optimizer.advanced_rules import ADVANCED_RULES, Category

    rule = ADVANCED_RULES.get(rule_id)
    if not rule:
        return None
    nc = _action_class("non_cost").value
    oc = _action_class("other_cost").value
    rs = _action_class("rightsize").value
    gov = _action_class("governance").value
    if rule.category == Category.COST:
        return RuleBehavior(oc, False, SCORING_INVESTIGATE)
    if rule.category == Category.GOVERNANCE:
        return RuleBehavior(gov, False, SCORING_INVESTIGATE)
    if rule.category in {Category.SECURITY, Category.RELIABILITY}:
        return RuleBehavior(nc, False, SCORING_MANUAL_REVIEW)
    if rule.category in {Category.COMPUTE, Category.STORAGE, Category.NETWORK, Category.KUBERNETES, Category.DATABASE}:
        return RuleBehavior(oc, False, SCORING_INVESTIGATE)
    return RuleBehavior(oc, False, SCORING_INVESTIGATE)


def get_rule_behavior(rule_id: str | None) -> RuleBehavior | None:
    rid = canonical_rule_id(rule_id).upper()
    if not rid:
        return None
    explicit = _explicit_overrides().get(rid)
    if explicit is not None:
        return explicit
    inferred = _infer_behavior(rid)
    if inferred is not None:
        return inferred
    return _fallback_from_advanced_rule(rid)


def classify_rule_action_class(rule_id: str | None) -> SavingsActionClass | None:
    behavior = get_rule_behavior(rule_id)
    if behavior is None:
        return None
    from app.savings_aggregation import SavingsActionClass

    try:
        return SavingsActionClass(behavior.action_class)
    except ValueError:
        return None


def is_waste_heatmap_rule(rule_id: str | None) -> bool:
    """True when a finding should appear on the waste heatmap."""
    behavior = get_rule_behavior(rule_id)
    if behavior is not None:
        return behavior.waste_heatmap
    rid = canonical_rule_id(rule_id).upper()
    if rid in _DATABASE_WASTE_RULE_IDS:
        return True
    return False


def scoring_action_for_rule(rule_id: str | None) -> str | None:
    behavior = get_rule_behavior(rule_id)
    return behavior.scoring_action if behavior else None


def scoring_action_for_rule_ids(rule_ids: set[str]) -> str | None:
    actions = {scoring_action_for_rule(rid) for rid in rule_ids}
    actions.discard(None)
    for preferred in _SCORING_PRIORITY:
        if preferred in actions:
            return preferred
    return None


def rule_ids_for_action_class(action_class: str) -> frozenset[str]:
    """All known advanced rules matching an action class — for tests and diagnostics."""
    from app.optimizer.advanced_rules import ADVANCED_RULES

    matched: set[str] = set()
    for rule_id in ADVANCED_RULES:
        behavior = get_rule_behavior(rule_id)
        if behavior and behavior.action_class == action_class:
            matched.add(rule_id)
    return frozenset(matched)


def rule_ids_for_waste_heatmap() -> frozenset[str]:
    from app.optimizer.advanced_rules import ADVANCED_RULES

    return frozenset(rid for rid in ADVANCED_RULES if is_waste_heatmap_rule(rid))
