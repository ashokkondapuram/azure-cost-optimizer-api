"""Backup resource optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.cost_utils import savings_from_factor


def analyze_recovery_vaults(
    engine,
    subscription_id: str,
    vaults: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("BACKUP_RETENTION_EXTENDED")
    if not rule or not rule.enabled:
        return out
    for vault in vaults:
        name = vault.get("name") or ""
        monthly = resource_cost(cost_by_resource, vault.get("id", ""))
        if monthly < 75:
            continue
        props = vault.get("properties") or {}
        out.append(engine._finding(
            rule=rule,
            subscription_id=subscription_id,
            resource=vault,
            detail=f"Recovery Services vault '{name}' has MTD spend of ${monthly:,.2f}.",
            recommendation="Shorten retention for non-critical workloads, remove orphaned backup items, and use archive tier for long-term copies.",
            savings=savings_from_factor(monthly, 0.20),
            waste_score=50,
            confidence=67,
            priority="P2",
            impact="Lower backup storage growth",
            evidence={"monthly_cost_usd": monthly, "provisioning_state": props.get("provisioningState")},
        ))
    return out
