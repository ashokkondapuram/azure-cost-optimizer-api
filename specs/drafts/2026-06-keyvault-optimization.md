# Key Vault cost optimization

**Status:** Draft  
**Author:** Engineering  
**Date:** Jun 30, 2026

## Problem statement

Key Vault recommendations mix security governance and cost optimization in a single extended rule, API hit thresholds are hardcoded, and idle vault findings never use MTD cost for savings. Users cannot tune Key Vault gates in Engine Config or see the same evidence depth as ACR, disks, and snapshots.

## Proposed solution

1. **Expand inventory** — sync SKU, purge protection, network access, and RBAC fields.
2. **7-day Monitor metrics** — `ServiceApiHit`, `Availability`, optional `ServiceApiResult`.
3. **Split rules** — protection governance, idle vault removal, Premium SKU review, high-ops caching counsel.
4. **Configurable thresholds** — `kv_api_hits_idle`, `kv_api_hits_high`, `min_monthly_savings_usd` per rule in Engine Config.
5. **MTD savings** — idle vault findings use full monthly cost from Cost Management.

## Data model changes

- Extend [`app/resources/security/keyvault.py`](../app/resources/security/keyvault.py) technical fetch spec fields.
- New module [`app/keyvault_utilization.py`](../app/keyvault_utilization.py).
- New extended rules: `KEYVAULT_IDLE_EXTENDED`, `KEYVAULT_PREMIUM_EXTENDED`, `KEYVAULT_HIGH_OPS_EXTENDED`.

## API changes

None (uses existing inventory sync and Monitor fetch paths).

## UI changes

- Engine Config exposes Key Vault threshold settings per rule.
- Finding evidence shows SKU, protection settings, API hits, and threshold values.

## Acceptance criteria

- [ ] Engine Config shows Key Vault thresholds for idle, premium, and high-ops rules.
- [ ] `KEYVAULT_PROTECTION_EXTENDED` only reports protection baseline gaps (no idle findings).
- [ ] `KEYVAULT_IDLE_EXTENDED` uses MTD cost for savings when API hits are below threshold.
- [ ] `KEYVAULT_PREMIUM_EXTENDED` blocks downgrade for production vaults or high API activity.
- [ ] `docs/RESOURCE_COST_MAPPING.md` and `docs/METRICS_AND_TRIGGERS.md` updated.
- [ ] Tests cover utilization helpers, analysis rules, and rule catalog settings.

## Out of scope

- Per-key / HSM key inventory (data-plane API).
- Managed HSM pool resources (`Microsoft.KeyVault/managedHsm`).
- Certificate renewal cost detection ($3/renewal).

## Dependencies

- Existing extended engine and Monitor 7-day fetch pipeline.
- Background rule-config re-analysis (`POST /optimize/config/{profile}/reanalyze`).
