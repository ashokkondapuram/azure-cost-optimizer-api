"""Disk Snapshots optimization analysis rules."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.snapshot_retention import (
    is_stale_snapshot,
    meets_snapshot_savings_gate,
    meets_snapshot_size_gate,
    snapshot_age_days,
    snapshot_created_at,
    snapshot_lineage_evidence,
    snapshot_size_gb,
    snapshot_threshold_evidence,
)

__all__ = [
    "analyze_snapshots",
    "snapshot_created_at",
    "snapshot_size_gb",
]


def analyze_snapshots(engine, subscription_id: str, snapshots: list[dict], cost_by_resource: dict[str, float]) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    snapshot_rule = engine.rules["SNAPSHOT_RETENTION_EXTENDED"]
    now = datetime.now(timezone.utc)
    for snapshot in snapshots:
        if not snapshot_rule.enabled:
            continue
        created_at = snapshot_created_at(snapshot)
        if not created_at:
            continue
        age_days = snapshot_age_days(snapshot, now=now)
        if age_days is None:
            continue
        if not is_stale_snapshot(
            snapshot,
            retention_days=snapshot_rule.snapshot_retention_days,
            now=now,
        ):
            continue
        if not meets_snapshot_size_gate(snapshot, min_size_gb=snapshot_rule.snapshot_min_size_gb):
            continue
        size_gb = snapshot_size_gb(snapshot)
        rid = snapshot.get("id") or ""
        savings = resource_cost(cost_by_resource, rid)
        if not meets_snapshot_savings_gate(
            savings,
            min_monthly_savings_usd=snapshot_rule.min_monthly_savings_usd,
        ):
            continue
        lineage = snapshot_lineage_evidence(snapshot)
        sku = lineage.get("sku") or ((snapshot.get("sku") or {}).get("name") if isinstance(snapshot.get("sku"), dict) else "")
        detail = (
            f"Snapshot '{snapshot.get('name')}' is {age_days} days old "
            f"({size_gb:g} GB"
            f"{f', {sku}' if sku else ''}"
            f") — exceeds the {snapshot_rule.snapshot_retention_days}-day retention threshold."
        )
        if lineage.get("incremental") is True:
            detail += " Incremental snapshot — validate the full chain before delete."
        out.append(engine._finding(
            rule=snapshot_rule,
            subscription_id=subscription_id,
            resource=snapshot,
            detail=detail,
            recommendation=(
                f"Delete or archive snapshots older than {snapshot_rule.snapshot_retention_days} days "
                "after validating recovery requirements."
            ),
            savings=savings,
            waste_score=46 if age_days < snapshot_rule.snapshot_retention_days * 2 else 58,
            confidence=82,
            priority="P2" if age_days >= snapshot_rule.snapshot_retention_days * 2 else "P3",
            impact="Reduces stale backup storage spend",
            evidence={
                "age_days": age_days,
                "size_gb": size_gb,
                "time_created": created_at.isoformat(),
                "monthly_cost_usd": savings,
                **lineage,
                **snapshot_threshold_evidence(snapshot_rule),
            },
        ))
    return out
