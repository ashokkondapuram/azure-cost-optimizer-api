"""Backup resource optimization analysis rules."""

from __future__ import annotations

from typing import Any

from app.cost_utils import resource_cost
from app.optimizer.core.finding import ExtendedFinding
from app.stub_engine_common import append_stub_draft
from it_services.backup_recoveryvault.engine.optimization_rules import (
    evaluate_backup_retention,
    evaluate_backup_vault_growth,
)


def analyze_recovery_vaults(
    engine,
    subscription_id: str,
    vaults: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    retention_rule = engine.rules.get("BACKUP_RETENTION_EXTENDED")
    growth_rule = engine.rules.get("BACKUP_VAULT_GROWTH_EXTENDED")
    for vault in vaults:
        monthly = resource_cost(cost_by_resource, vault.get("id", ""))
        append_stub_draft(out, engine, subscription_id, vault, retention_rule, evaluate_backup_retention(vault, monthly, retention_rule))
        append_stub_draft(out, engine, subscription_id, vault, growth_rule, evaluate_backup_vault_growth(vault, monthly, growth_rule))
    return out
