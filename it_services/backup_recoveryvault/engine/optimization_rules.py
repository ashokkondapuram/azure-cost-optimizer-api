"""Recovery Services vault optimization decision rules — retention and storage growth."""

from __future__ import annotations

from typing import Any

from app.service_thresholds import threshold_values
from app.stub_engine_common import StubFindingDraft, cost_finding_draft

_CANONICAL = "backup/recoveryvault"


def _thresholds(rule: Any) -> dict[str, float]:
    return threshold_values(
        rule,
        _CANONICAL,
        min_cost="min_monthly_cost_usd",
        savings_factor="savings_factor",
        growth_factor="growth_savings_factor",
        min_savings="min_monthly_savings_usd",
    )


def evaluate_backup_retention(
    vault: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    props = vault.get("properties") or {}
    return cost_finding_draft(
        rule_id="BACKUP_RETENTION_EXTENDED",
        resource=vault,
        monthly=monthly_cost,
        detail_suffix="Review retention policies and protected item inventory.",
        recommendation=(
            "Shorten retention for non-critical workloads, remove orphaned backup items, "
            "and use archive tier for long-term copies."
        ),
        savings_factor=th["savings_factor"],
        waste_score=50,
        priority="P2",
        impact="Lower backup storage growth",
        min_savings=th["min_savings"],
        extra_evidence={"provisioning_state": props.get("provisioningState")},
    )


def evaluate_backup_vault_growth(
    vault: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    growth_threshold = th["min_cost"] * 2
    if monthly_cost < growth_threshold:
        return None
    props = vault.get("properties") or {}
    return cost_finding_draft(
        rule_id="BACKUP_VAULT_GROWTH_EXTENDED",
        resource=vault,
        monthly=monthly_cost,
        detail_suffix="Vault backup storage cost exceeds growth review threshold.",
        recommendation=(
            "Audit protected items, remove stale backups, and apply tiered retention "
            "for non-critical workloads."
        ),
        savings_factor=th["growth_factor"],
        waste_score=55,
        priority="P2",
        impact="Control backup storage growth",
        min_savings=th["min_savings"],
        extra_evidence={
            "provisioning_state": props.get("provisioningState"),
            "growth_threshold_usd": growth_threshold,
        },
    )
