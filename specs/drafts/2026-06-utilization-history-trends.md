# Utilization history and trend analysis (T2-A)

**Status:** Draft  
**Author:** Engineering  
**Date:** Jun 30, 2026

## Problem statement

The optimization engine operates on 7-day point-in-time snapshots. It cannot distinguish a VM that has been idle for months from one that just entered a seasonal trough, or flag databases whose storage is growing rapidly. Without historical utilization, recommendations are reactive and can misfire on upward-trending workloads.

## Proposed solution

1. **Persist utilization snapshots** after each analysis run into `resource_utilization_history`.
2. **Trend queries** compute slope, volatility, and 4-week projections from weekly snapshots (6-month retention).
3. **Engine gates** — VM downsize requires stable/shrinking CPU trend when 4+ weeks of history exist; storage engines can use `storage_capacity_warning()` (T2-D builds on this).

## Data model changes

New table `resource_utilization_history`:

| Column | Type | Notes |
|--------|------|-------|
| subscription_id | string | indexed |
| resource_id | ARM id | indexed |
| metric_name | string | e.g. `avg_cpu_pct` |
| snapshot_date | YYYY-MM-DD | unique per resource/metric/day |
| value_avg / value_max / value_min | float | nullable |
| period_days | int | default 7 |

## API changes

None in T2-A. Future: `GET /metrics/trends/{resource_id}` for drawer display.

## UI changes

None in T2-A. Finding evidence includes `utilization_trend`, `projected_cpu_4w` on VM underutilization findings when history exists.

## Acceptance criteria

- [x] Table created via `migrate_schema()` on existing databases.
- [x] Orchestrator persists metrics after each `run_db_analysis` completion.
- [x] Same-day re-runs upsert rather than duplicate rows.
- [x] Rows older than 180 days are pruned on persist.
- [x] `utilization_trend()` returns slope, volatility, projection with ≥4 weekly points.
- [x] VM downsize suppressed when CPU trend is `growing` and history is sufficient.
- [x] Tests cover persist, trend classification, and downsize gate.

## Out of scope

- Workload fingerprinting (T2-B)
- Topology discovery (T2-C)
- Demand forecasting service (T2-D) — uses this table as input
- Portfolio analysis (T2-E)
- Execution tracking (T2-F)

## Dependencies

- Tier 1 peak metrics (`max_cpu_pct`, etc.) must be present in `_technical_facts` for rich snapshots.

## Open questions

- Should we collapse avg/max into one row per metric family vs separate rows? Current: separate rows per fact key.
- Weekly vs daily snapshot cadence — currently one snapshot per analysis run date (typically weekly in production).
