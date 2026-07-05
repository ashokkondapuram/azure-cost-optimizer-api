# Container registry cost optimization

**Status:** Draft  
**Author:** Engineering  
**Date:** Jun 30, 2026

## Problem statement

Azure Container Registry (ACR) recommendations are shallow: only two extended rules exist, geo-replication detection does not work (child resources are not synced), SKU downgrade ignores Premium-only features, and pull/storage thresholds are hardcoded. Users cannot tune ACR gates in Engine Config or see the same evidence depth as managed disks and snapshots.

## Proposed solution

1. **Expand inventory** — sync SKU, zone redundancy, network rules, retention policy, private endpoints, and geo-replication child resources.
2. **7-day Monitor metrics** — `TotalPullCount`, `StorageUsed`, `TotalPushCount` for activity and storage gates.
3. **Cost decision matrix** — SKU right-sizing, geo-replication review, high-storage cleanup, retention policy governance.
4. **Configurable thresholds** — `acr_pull_count_low`, `acr_storage_high_gb`, `acr_push_count_low`, `min_monthly_savings_usd` per rule in Engine Config.
5. **Safety gates** — block SKU downgrade when Premium-only features are active.

## Data model changes

- Extend [`app/resources/containers/acr.py`](../app/resources/containers/acr.py) technical fetch spec fields.
- New module [`app/acr_utilization.py`](../app/acr_utilization.py).
- Replication list attached during sync in `properties._replications` / `replicationCount`.
- New extended rules: `ACR_STANDARD_EXTENDED`, `ACR_STORAGE_HIGH_EXTENDED`, `ACR_RETENTION_DISABLED_EXTENDED`.

## API changes

None (uses existing inventory sync and Monitor fetch paths).

## UI changes

- Engine Config exposes new ACR threshold settings per rule.
- Finding evidence shows SKU, replication count, storage, pull count, and active premium blockers.

## Acceptance criteria

- [ ] Engine Config shows ACR thresholds for all five ACR rules.
- [ ] Findings include threshold evidence and inventory blockers when SKU downgrade is blocked.
- [ ] `ACR_GEO_REPLICATION_EXTENDED` fires when geo-replication child resources are synced.
- [ ] SKU downgrade is blocked when geo-replication, private link, IP rules, zone redundancy, or retention policy require Premium.
- [ ] `docs/RESOURCE_COST_MAPPING.md` and `docs/METRICS_AND_TRIGGERS.md` updated.
- [ ] Tests cover utilization helpers, analysis rules, and rule catalog settings.

## Out of scope

- Per-repository / manifest catalog API for stale tagged images.
- Azure Retail pricing SKU diff (use MTD cost factors until retail helper exists).
- Standard-engine inventory-only ACR rule without Monitor.

## Dependencies

- Existing extended engine and Monitor 7-day fetch pipeline.
- Background rule-config re-analysis (`POST /optimize/config/{profile}/reanalyze`).
