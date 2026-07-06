"""Waste Heatmap — aggregate idle/underutilised findings by resource group and type.

Returns a heatmap matrix: rows = resource groups, columns = resource types,
cell value = total estimated monthly waste (USD) from open findings.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from app.models import OptimizationFinding


def get_waste_heatmap(db: Session, subscription_id: str | None = None) -> dict[str, Any]:
    """Return heatmap data grouped by resource_group x resource_type."""
    q = db.query(OptimizationFinding).filter(
        OptimizationFinding.status == "open"
    )
    if subscription_id:
        q = q.filter(OptimizationFinding.subscription_id == subscription_id)

    findings = q.all()

    # Accumulate waste per (resource_group, resource_type) cell.
    cell: dict[tuple[str, str], float] = defaultdict(float)
    rg_set: set[str] = set()
    rt_set: set[str] = set()

    for f in findings:
        rg = (f.resource_group or "(unknown)").lower()
        rt = (f.resource_type or "other").lower()
        waste = float(f.estimated_monthly_savings or 0)
        cell[(rg, rt)] += waste
        rg_set.add(rg)
        rt_set.add(rt)

    resource_groups = sorted(rg_set)
    resource_types = sorted(rt_set)

    rows = []
    for rg in resource_groups:
        row = {"resource_group": rg, "cells": []}
        for rt in resource_types:
            row["cells"].append(
                {"resource_type": rt, "waste_usd": round(cell.get((rg, rt), 0), 2)}
            )
        rows.append(row)

    total = sum(cell.values())
    return {
        "resource_types": resource_types,
        "rows": rows,
        "total_waste_usd": round(total, 2),
        "finding_count": len(findings),
    }
