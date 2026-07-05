"""Resource dependency graph analysis and blast-radius computation."""
from __future__ import annotations

import json
from collections import defaultdict, deque
from typing import Any

from sqlalchemy.orm import Session

from app.models import ResourceDependency, ResourceSnapshot
from app.optimizer.scoring_weights import BUSINESS_TAG_KEYS, CRITICALITY_RANK, SLA_TAG_KEYS
from app.utils import norm_arm_id, parse_tags_json

_COMPLIANCE_LOCK_VALUES = frozenset({"true", "yes", "1", "locked"})


def _tag_value(tags: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        if key in tags:
            return tags[key]
    return None


def infer_criticality_from_tags(tags: dict[str, str], *, monthly_cost: float = 0.0) -> str:
    """Infer criticality: critical | high | medium | low."""
    biz = _tag_value(tags, BUSINESS_TAG_KEYS)
    if biz in CRITICALITY_RANK:
        if CRITICALITY_RANK[biz] >= 4:
            return "critical"
        if CRITICALITY_RANK[biz] >= 3:
            return "high"
        if CRITICALITY_RANK[biz] >= 2:
            return "medium"
        return "low"

    env = _tag_value(tags, ("environment", "env"))
    if env in {"production", "prod"}:
        return "high"
    if env in {"staging", "stage", "uat"}:
        return "medium"
    if env in {"dev", "development", "test", "qa"}:
        return "low"

    if monthly_cost >= 5000:
        return "high"
    if monthly_cost >= 1000:
        return "medium"
    return "low"


def is_compliance_locked(tags: dict[str, str]) -> bool:
    for key in ("compliance-locked", "compliancelocked", "change-locked"):
        val = tags.get(key)
        if val and val.lower() in _COMPLIANCE_LOCK_VALUES:
            return True
    return False


def sla_tier(tags: dict[str, str]) -> str:
    raw = _tag_value(tags, SLA_TAG_KEYS) or "none"
    if raw in {"gold", "platinum"}:
        return "gold"
    if raw in {"silver"}:
        return "silver"
    if raw in {"bronze"}:
        return "bronze"
    return "none"


def build_adjacency(
    dependencies: list[ResourceDependency],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return (outbound, inbound) adjacency lists."""
    outbound: dict[str, list[str]] = defaultdict(list)
    inbound: dict[str, list[str]] = defaultdict(list)
    for dep in dependencies:
        src = norm_arm_id(dep.source_resource_id)
        tgt = norm_arm_id(dep.target_resource_id)
        if not src or not tgt:
            continue
        outbound[src].append(tgt)
        inbound[tgt].append(src)
    return outbound, inbound


def transitive_dependents(
    resource_id: str,
    inbound: dict[str, list[str]],
    *,
    max_depth: int = 5,
) -> set[str]:
    """Resources that transitively depend on (route through) this resource."""
    start = norm_arm_id(resource_id)
    seen: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    while queue:
        node, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for parent in inbound.get(node, []):
            if parent in seen:
                continue
            seen.add(parent)
            queue.append((parent, depth + 1))
    return seen


def analyze_dependencies(
    db: Session,
    subscription_id: str,
    resource_id: str,
    *,
    snapshots_by_id: dict[str, ResourceSnapshot] | None = None,
) -> dict[str, Any]:
    """Dependency analysis for a single resource."""
    sub = subscription_id.strip().lower()
    rid = norm_arm_id(resource_id)

    deps = (
        db.query(ResourceDependency)
        .filter(ResourceDependency.subscription_id == sub)
        .all()
    )
    outbound, inbound = build_adjacency(deps)

    direct_out = list(dict.fromkeys(outbound.get(rid, [])))
    direct_in = list(dict.fromkeys(inbound.get(rid, [])))
    transitive = transitive_dependents(rid, inbound)

    if snapshots_by_id is None:
        snapshots_by_id = {
            norm_arm_id(s.resource_id): s
            for s in db.query(ResourceSnapshot).filter(ResourceSnapshot.subscription_id == sub).all()
        }

    criticalities: list[str] = []
    for dep_rid in direct_out + direct_in + list(transitive):
        snap = snapshots_by_id.get(dep_rid)
        tags = parse_tags_json(snap.tags_json if snap else None)
        cost = float(snap.monthly_cost_usd or 0) if snap else 0.0
        criticalities.append(infer_criticality_from_tags(tags, monthly_cost=cost))

    max_crit = "low"
    for c in criticalities:
        if CRITICALITY_RANK.get(c, 0) > CRITICALITY_RANK.get(max_crit, 0):
            max_crit = c

    blast_radius = len(transitive) + len(direct_out)

    snap = snapshots_by_id.get(rid)
    tags = parse_tags_json(snap.tags_json if snap else None)

    return {
        "resource_id": rid,
        "direct_outbound": direct_out,
        "direct_inbound": direct_in,
        "transitive_dependent_count": len(transitive),
        "blast_radius": blast_radius,
        "max_criticality": max_crit,
        "compliance_locked": is_compliance_locked(tags),
        "sla_tier": sla_tier(tags),
    }


def enrich_dependency_criticality(
    db: Session,
    subscription_id: str,
) -> int:
    """Update criticality column on dependency edges from target resource tags."""
    sub = subscription_id.strip().lower()
    snapshots = {
        norm_arm_id(s.resource_id): s
        for s in db.query(ResourceSnapshot).filter(ResourceSnapshot.subscription_id == sub).all()
    }
    deps = db.query(ResourceDependency).filter(ResourceDependency.subscription_id == sub).all()
    updated = 0
    for dep in deps:
        tgt = snapshots.get(norm_arm_id(dep.target_resource_id))
        tags = parse_tags_json(tgt.tags_json if tgt else None)
        cost = float(tgt.monthly_cost_usd or 0) if tgt else 0.0
        crit = infer_criticality_from_tags(tags, monthly_cost=cost)
        if dep.criticality != crit:
            dep.criticality = crit
            updated += 1
    if updated:
        db.commit()
    return updated
