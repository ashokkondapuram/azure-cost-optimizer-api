"""Key Vault optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.resource_engines.runtime.base import ResourceSubEngine
from app.optimizer.resource_engines.security.keyvault.analysis import analyze_keyvaults


class KeyVaultSubEngine(ResourceSubEngine):
    component = "Key Vault"
    bucket_keys = ('keyvaults',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        vaults = self.prepare_resources(buckets.get("keyvaults") or [])
        findings = analyze_keyvaults(
            self.engine,
            self.ctx.subscription_id,
            vaults,
            self.ctx.cost_by_resource,
        )
        return self.enhance_findings(findings, vaults)
