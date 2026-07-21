"""Backup optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from it_services.backup_recoveryvault.engine.analysis import analyze_recovery_vaults


class BackupSubEngine(ResourceSubEngine):
    component = "Backup"
    bucket_keys = ("recovery_vaults",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        vaults = self.prepare_resources(buckets.get("recovery_vaults") or [])
        findings = analyze_recovery_vaults(
            self.engine, self.ctx.subscription_id, vaults, self.ctx.cost_by_resource,
        )
        return self.enhance_findings(findings, vaults)
