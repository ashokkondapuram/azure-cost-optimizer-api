# Metrics determination, display, and cost/performance triggers

**Status:** Draft  
**Author:** Engineering  
**Date:** Jun 29, 2026

## Problem statement

Optimization recommendations depend on Azure Monitor metrics, but metric definitions, labels, and display logic are scattered across backend profiles, `METRIC_DEFS`, and frontend formatters. Users see inconsistent labels, duplicate metrics in drawers vs findings, admin-only access errors, and no explanation of which metrics drive cost vs performance outcomes.

## Proposed solution

1. **Single metrics catalog** — extend `UtilizationMetric` with unit, display, and impact metadata; expose via `/metrics/profiles` and unified resource metrics API.
2. **Unified display** — all authenticated users see profile-appropriate metrics in the resource drawer with graceful empty states.
3. **Trigger registry** — map metrics to rule thresholds and cost/performance effects; surface in drawer and recommendation evidence.

## Data model changes

- Extend `UtilizationMetric` with `unit`, `primary_stat`, `display_stats`, `impact`.
- New modules: `app/metrics_catalog.py`, `app/metrics_triggers.py`.
- API response adds `metrics`, `derived`, `data_quality`, `triggers`.

## API changes

- `GET /metrics/resource/auto` — authenticated (not admin-only); unified payload shape.
- `GET /metrics/profiles` — enriched catalog entries.
- Bulk subscription/type fetch remains admin-only.

## UI changes

- `ResourceAzureMetrics`, `ResourceMetricsDetailTable` — catalog-driven formatting and empty states.
- `MetricsTriggersPanel` — “What this means” below metrics table.
- `FindingEvidence` — hide performance metrics duplicated in live drawer; show trigger reasons.
- `VmSizingInsight` — align CPU/memory display with unified metrics formatting.

## Acceptance criteria

- [ ] All 28 `MONITOR_PROFILE` types expose unit + impact in catalog API.
- [ ] Authenticated viewers can load `/metrics/resource/auto` without 403.
- [ ] Drawer shows consistent layout for profiled types; clear message for unprofiled types.
- [ ] Derived metrics (`avg_memory_pct`, `storage_pct` when computable) appear in API `derived`.
- [ ] Trigger registry covers rules in `RULE_METRIC_PROFILES` with matching thresholds.
- [ ] Recommendation cards show trigger metric, value, and threshold when available.
- [ ] `docs/METRICS_AND_TRIGGERS.md` generated from registry.
- [ ] `docs/RESOURCE_COST_MAPPING.md` maps each resource type to cost-driving properties and metrics.
- [ ] Tests cover catalog completeness, auth, formatting, and trigger alignment.

## Out of scope

- New Azure Monitor profiles for Databricks, Synapse, ML, snapshot, NSG.
- List-page inline utilization columns.
- Auto-remediation or alerting.
