"""Waste Heatmap — surface under-utilised / idle resources grouped by
resource-group and resource-type so operators can spot waste hotspots.

Reads from the ``resource_snapshots`` table and joins the latest
``optimization_findings`` to build a heatmap cell per (resource_group,
resource_type) pair together with a waste score.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_waste_heatmap(
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
            COUNT(DISTINCT r.id)                    AS resource_count,
            COUNT(f.id)                             AS finding_count,
            COALESCE(SUM(f.estimated_savings_usd), 0) AS total_savings
        FROM resource_snapshots r
        LEFT JOIN optimization_findings f
            ON  f.resource_id = r.resource_id
            AND f.status      IN ('open', 'acknowledged')
        WHERE r.is_active = 1
        {sub_clause}
        GROUP BY r.resource_group, r.resource_type
        ORDER BY total_savings DESC, finding_count DESC
        LIMIT :lim
        """
    )
    params: dict[str, Any] = {"lim": limit_groups * 5}
    if subscription_id:
        params["sub"] = subscription_id

    try:
        rows = db.execute(sql, params).fetchall()
    except Exception:
        rows = []

    cells: list[dict] = []
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
