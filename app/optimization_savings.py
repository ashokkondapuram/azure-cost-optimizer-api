"""Shared distinct monthly savings rollups for optimization hub surfaces."""
from __future__ import annotations

from typing import Any

from app.utils import norm_arm_id


def distinct_monthly_savings_by_resource(
    rows: list[Any],
    *,
    resource_key: str = "resource_id",
    savings_key: str = "estimated_monthly_savings",
) -> float:
    """Sum savings once per normalized resource (max when duplicates exist)."""
    by_resource: dict[str, float] = {}
    for row in rows:
        if isinstance(row, tuple):
            rid, savings = row
        else:
            rid = getattr(row, resource_key, None) if not isinstance(row, dict) else row.get(resource_key)
            savings = getattr(row, savings_key, None) if not isinstance(row, dict) else row.get(savings_key)
        key = norm_arm_id(rid) or str(rid or "").strip().lower()
        if not key:
            continue
        amount = float(savings or 0.0)
        by_resource[key] = max(by_resource.get(key, 0.0), amount)
    return round(sum(by_resource.values()), 2)


def distinct_action_savings(rows: list[Any]) -> float:
    return distinct_monthly_savings_by_resource(
        rows,
        resource_key="resource_id",
        savings_key="estimated_monthly_savings",
    )


def distinct_scoreboard_savings(rows: list[Any]) -> float:
    return distinct_monthly_savings_by_resource(
        rows,
        resource_key="resource_id",
        savings_key="cost_savings_monthly",
    )
