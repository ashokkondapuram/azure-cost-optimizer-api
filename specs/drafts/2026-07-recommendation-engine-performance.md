# Recommendation engine — performance & coverage

**Status:** Draft (Phase 1 implemented Jul 7, 2026)  
**Author:** Engineering  
**Date:** Jul 7, 2026

## Problem statement

Analysis and sync paths load full tables into memory and use nested O(n×m) loops. Large subscriptions (5K+ resources) see 2–3 minute analysis runs and memory spikes during sync.

## Approved phases

### Phase 1 — Engine performance quick wins (DONE)

| ID | Change | Status |
|----|--------|--------|
| A2 | Pre-build AKS node metrics index by pool prefix | Done |
| A5 | Iterate only resources with loaded metrics | Done |
| A7 | Cache `get_monitor_profile` by `(arm_type, canonical)` | Done |
| A1 | `yield_per(500)` on sync/deactivate/dedup queries | Done |
| A4 | Streaming dedup (paired with A1) | Done |

### Phase 2 — Performance + config (approved, not started)

| ID | Change |
|----|--------|
| A3 | Batch JSON parsing in `metrics_loader.py` |
| A6 | Parallel resource enrichment (thread-safety review required) |
| C1 | Scoring customization (`waste_score_multiplier`) |
| C5 | Expose `min_monthly_savings_usd` on base rules API |

### Phase 3 — Rule expansion (approved, not started)

| ID | Change |
|----|--------|
| B2 | Database advanced rules (elastic pool, hybrid benefit) |
| C2 | Tag/RG/type exclusion filters |
| C3 | Prod vs nonprod severity from tags |
| B1 | Network rules (extend `resource_engines/network/`) |

### Phase 4 — Governance & UI (deferred — spec required)

C6–C10, B3, B4, C7, C8, C9

## Backend performance (parallel track)

| Phase | Status |
|-------|--------|
| Backend Tier 1 (pagination, currency, cost overlays) | Done Jul 7, 2026 |
| Backend Tier 2 (cursor pagination API + UI) | Approved |
| Backend Tier 3 (cleanup items 7, 8, 11, 14, 15) | Approved parallel |

## Acceptance criteria — Phase 1

- [x] `_dedupe_resource_snapshots` uses `yield_per`, not `.all()`
- [x] AKS idle-node check uses pre-built prefix index
- [x] Monitor facts loop only processes resources with metrics payload
- [x] Profile lookups cached per ARM type
- [ ] Benchmark: analysis p95 recorded before/after on 5K+ sub

## Verification

```bash
pytest tests/test_db_sync_prune.py tests/test_analysis_engine.py tests/test_perf_improvements.py -q
```

## Out of scope (Phase 1)

- Schema changes for evidence storage (A3)
- Parallel enrichment without session isolation review (A6)
- New rule modules (Tier B)
