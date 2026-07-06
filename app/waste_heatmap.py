"""Waste Heatmap — surface under-utilised / idle resources grouped by
resource-group and resource-type so operators can spot waste hotspots.

Reads from the synced ``resources`` table and joins the latest
``optimization_findings`` to build a heatmap cell per (resource_group,
resource_type) pair together with a waste score.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# Findings with these statuses are counted as active waste.
_WASTE_STATUSES = {"open", "acknowledged"}
# Severity multipliers used when computing a composite waste score.
_SEVERITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def build_waste_heatmap(
    db: Session,
    subscription_id: str | None = None,
    limit_groups: int = 20,
) -> dict[str, Any]:
    """Return heatmap cells ranked by waste score."""
    sub_clause = "AND r.subscription_id = :sub" if subscription_id else ""
    sql = text(
        f"""
        SELECT
            r.resource_group,
            r.resource_type,
            COUNT(DISTINCT r.id)          AS resource_count,
            COUNT(f.id)                   AS finding_count,
            COALESCE(SUM(f.estimated_savings), 0) AS total_savings
        FROM resources r
        LEFT JOIN optimization_findings f
            ON  f.resource_id = r.arm_resource_id
            AND f.status      IN ('open', 'acknowledged')
        WHERE r.resource_group IS NOT NULL
        {sub_clause}
        GROUP BY r.resource_group, r.resource_type
        ORDER BY total_savings DESC, finding_count DESC
        LIMIT :lim
        """
    )
    params: dict[str, Any] = {"lim": limit_groups * 5}  # rows, not groups
    if subscription_id:
        params["sub"] = subscription_id

    try:
        rows = db.execute(sql, params).fetchall()
    except Exception:
        rows = []

    # Aggregate into (resource_group, resource_type) cells.
    cells: list[dict] = []
    seen_groups: set[str] = set()
    for row in rows:
        rg, rt, rc, fc, ts = row[0], row[1], int(row[2]), int(row[3]), float(row[4])
        cells.append(
            {
                "resource_group": rg or "(unknown)",
                "resource_type": rt or "(unknown)",
                "resource_count": rc,
                "finding_count": fc,
                "total_savings": round(ts, 2),
                "waste_score": round((fc * 2 + ts / 10), 1),
            }
        )
        seen_groups.add(rg or "")

    # Top groups by aggregate savings for the summary bar.
    group_totals: dict[str, float] = defaultdict(float)
    for c in cells:
        group_totals[c["resource_group"]] += c["total_savings"]
    top_groups = [
        {"resource_group": g, "total_savings": round(v, 2)}
        for g, v in sorted(group_totals.items(), key=lambda x: -x[1])[:limit_groups]
    ]

    return {
        "subscription_id": subscription_id,
        "cells": cells,
        "top_groups": top_groups,
        "total_cells": len(cells),
    }
