"""SQL-level inventory exclusions (tags, resource groups, types)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Text, cast, func, not_, or_
from sqlalchemy.orm import Query

from app.db_types import is_postgres_engine
from app.models import ResourceSnapshot
from app.optimizer.engine_filters import merge_global_config


def _blocked_tag_values(blocked_vals: Any) -> set[str]:
    if isinstance(blocked_vals, set):
        return {str(v).strip().lower() for v in blocked_vals if str(v).strip()}
    return {str(v).strip().lower() for v in (blocked_vals or []) if str(v).strip()}


def _tag_value_not_blocked(column, tag_key: str, blocked: set[str]):
    """Exclude rows whose tag value is in the blocked set."""
    blocked = {v.lower() for v in blocked}
    if not blocked:
        return None
    if is_postgres_engine():
        from sqlalchemy.dialects.postgresql import JSONB

        extracted = func.lower(func.coalesce(cast(column, JSONB)[tag_key].astext, ""))
        return not_(extracted.in_(blocked))
    extracted = func.lower(func.coalesce(func.json_extract(column, f"$.{tag_key}"), ""))
    return not_(extracted.in_(blocked))


def _resource_group_exclusion_clause(patterns: list[str]):
    """Exclude rows whose resource group matches any configured regex."""
    clean = [str(p).strip() for p in (patterns or []) if str(p).strip()]
    if not clean:
        return None
    if is_postgres_engine():
        return not_(or_(*[ResourceSnapshot.resource_group.op("~*")(pat) for pat in clean]))
    # SQLite: best-effort LIKE for simple wildcard patterns
    like_parts = []
    for pat in clean:
        if any(ch in pat for ch in ".*+?[](){}|^$\\"):
            continue
        like_parts.append(ResourceSnapshot.resource_group.ilike(pat.replace("*", "%")))
    return not_(or_(*like_parts)) if like_parts else None


def apply_inventory_exclusions(query: Query, global_config: dict[str, Any] | None = None) -> Query:
    """Apply tag/RG/type exclusions at the DB query layer."""
    cfg = merge_global_config(global_config)

    excluded_types = {t.strip().lower() for t in (cfg.get("exclude_resource_types") or []) if t}
    if excluded_types:
        query = query.filter(ResourceSnapshot.resource_type.notin_(sorted(excluded_types)))

    for tag_key, blocked_vals in (cfg.get("exclude_tags") or {}).items():
        clause = _tag_value_not_blocked(ResourceSnapshot.tags_json, str(tag_key), _blocked_tag_values(blocked_vals))
        if clause is not None:
            query = query.filter(clause)

    rg_clause = _resource_group_exclusion_clause(cfg.get("exclude_resource_group_patterns") or [])
    if rg_clause is not None:
        query = query.filter(rg_clause)

    return query
