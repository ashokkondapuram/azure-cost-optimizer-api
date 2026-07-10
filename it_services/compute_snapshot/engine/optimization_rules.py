"""Disk snapshot optimization decision rules — archive and long-term retention."""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any

from app.compute_pricing import estimate_snapshot_archive_savings
from app.snapshot_retention import snapshot_age_days, snapshot_created_at, snapshot_size_gb
from app.snapshot_retention_catalog import optimization_thresholds


@dataclass(frozen=True)
class ComputeFindingDraft:
    rule_id: str
    detail: str
    recommendation: str
    savings: float
    waste_score: int
    confidence: int
    priority: str
    impact: str
    evidence: dict[str, Any]


def _thresholds(rule: Any) -> dict[str, float]:
    defaults = optimization_thresholds()
    return {
        "archive_days": float(getattr(rule, "snapshot_archive_days", defaults.get("archive_candidate_days", 180.0))),
        "delete_days": float(getattr(rule, "snapshot_delete_days", defaults.get("delete_candidate_days", 365.0))),
        "min_size_gb": float(getattr(rule, "snapshot_min_size_gb", defaults.get("min_size_gb", 10.0))),
        "min_savings": float(getattr(rule, "min_monthly_savings_usd", defaults.get("min_monthly_savings_usd", 2.0))),
    }


def evaluate_snapshot_archive_candidate(
    snapshot: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> ComputeFindingDraft | None:
    th = _thresholds(rule)
    created_at = snapshot_created_at(snapshot)
    if not created_at:
        return None
    age_days = snapshot_age_days(snapshot, now=datetime.now(timezone.utc))
    if age_days is None or age_days < th["archive_days"]:
        return None
    size_gb = snapshot_size_gb(snapshot)
    if size_gb < th["min_size_gb"]:
        return None
    name = snapshot.get("name") or ""
    delete_mode = age_days >= th["delete_days"]
    savings = estimate_snapshot_archive_savings(
        monthly_cost if monthly_cost >= th["min_savings"] else None,
        size_gb,
        delete_mode=delete_mode,
        min_savings=th["min_savings"],
    )
    if savings <= 0:
        return None
    priority = "P2" if delete_mode else "P3"
    action = "Delete" if delete_mode else "Archive to cool blob storage"
    return ComputeFindingDraft(
        rule_id="SNAPSHOT_ARCHIVE_EXTENDED",
        detail=(
            f"Snapshot '{name}' is {age_days} days old ({size_gb:g} GB) — "
            f"exceeds {int(th['archive_days'])}-day archive review threshold."
        ),
        recommendation=f"{action} after validating recovery requirements and backup policy compliance.",
        savings=savings,
        waste_score=60 if age_days >= th["delete_days"] else 48,
        confidence=85,
        priority=priority,
        impact="Long-retained snapshots accumulate per-GB monthly charges",
        evidence={
            "age_days": age_days,
            "size_gb": size_gb,
            "archive_threshold_days": th["archive_days"],
            "delete_threshold_days": th["delete_days"],
            "monthly_cost_usd": monthly_cost,
        },
    )
