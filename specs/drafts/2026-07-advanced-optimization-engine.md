# Advanced optimization engine

**Status:** Draft — Phase 4 complete  
**Author:** Engineering  
**Date:** Jul 3, 2026  
**Branch:** `dev-slot`  
**Related:**
- [`specs/approved/2026-06-unified-optimization-engine.md`](../approved/2026-06-unified-optimization-engine.md)
- [`specs/drafts/2026-07-azure-advisor-integration.md`](2026-07-azure-advisor-integration.md)

## Problem statement

Single-signal optimization (Advisor alone, cost alone, or metrics alone) misses dependency risk, workload burstiness, SLA constraints, and historical trends. Unsafe or low-ROI changes get proposed when context is incomplete.

**Goal:** Score every resource across multiple dimensions (cost, safety, effort, workload, business), assign rollout tiers, and stage changes with observation windows — running in **advisory mode** first alongside the simpler Advisor workflow.

## Proposed solution

1. **Profile** workloads and dependency blast radius (extend existing modules).
2. **Score** resources multi-dimensionally → `optimization_scoring`.
3. **Stage** approved actions by tier → `optimization_rollout_stages` (Phase 2).
4. **Observe** post-change metrics; auto-expand or rollback (Phase 2).
5. **UI:** scoreboard, resource deep-dive, rollout monitor (Phases 3–4).

Deploy **parallel** to simple Advisor integration — no breaking changes.

---

## Resolved design decisions

### 1. `historical_resource_snapshots` — **deferred**

Phase 1 reads from existing tables:

| Signal | Source |
|--------|--------|
| Utilization trends | `resource_utilization_history` via `utilization_history.py` |
| Cost trend | `resource_snapshots.monthly_cost_usd` + `cost_by_resource` |
| Daily roll-up table | Add only if scoreboard queries exceed 2s on prod data |

### 2. Scoring weights — **constants + env override**

Default weights (sum = 1.0), defined in `app/optimizer/scoring_weights.py`:

| Dimension | Weight | Notes |
|-----------|--------|-------|
| Cost | 0.30 | Savings potential + confidence |
| Safety | 0.25 | Inverted risk (100 − risk score) |
| Effort | 0.15 | Implementation complexity |
| Workload | 0.20 | Stability / predictability |
| Business | 0.10 | Tag-derived criticality |

Override via env `ADVANCED_ENGINE_WEIGHTS` as JSON, e.g. `{"cost":0.35,"safety":0.25,...}`.

### 3. Tier thresholds

| Tier | Overall score | Performance risk | Blast radius | Other |
|------|---------------|------------------|--------------|-------|
| `tier1_safe` | > 75 | < 20 | ≤ 1 | No SLA-lock tags |
| `tier2_balanced` | > 60 | < 40 | ≤ 3 | — |
| `tier3_risky` | > 40 | any | any | Not blocked |
| `blocked` | ≤ 40 | — | — | OR `sla-tier`/`compliance-locked` tags OR critical inbound deps |

### 4. Tag governance (business + safety dimensions)

Recognized tag keys (case-insensitive, first match wins):

| Tag key | Values | Effect |
|---------|--------|--------|
| `business-criticality` | critical, high, medium, low | Maps to business score |
| `sla-tier` | gold, silver, bronze, none | Gold → SLA risk 90; blocks tier 1 |
| `environment` | production, prod, staging, dev, test | Production lowers business score |
| `compliance-locked` | true, yes, 1 | Forces `blocked` tier |
| `cost-center` | any | Used for priority only (informational) |

Missing tags → neutral defaults (business score 50, no SLA block).

### 5. Workload type mapping

Extend `workload_classifier.py` output → persisted `workload_type`:

| Classifier class | Persisted type |
|------------------|----------------|
| zombie, idle | steady |
| batch | bursty |
| interactive | interactive |
| database, analytics | steady |

Burstiness score: `min(100, (max_cpu − avg_cpu) / max(avg_cpu, 1) × 25)`.

### 6. Advisor Phase C

Advanced engine does **not** replace `decision_engine.py`. Both run in parallel; `optimization_scoring.primary_action` may differ from `optimization_actions.action_type` during validation.

---

## What already exists (reuse)

| Plan item | Current state |
|-----------|---------------|
| `resource_dependencies` | `ResourceDependency` — extend with `criticality` per edge |
| Workload classification | `workload_classifier.py` — extend via `workload_profiler.py` |
| Resource graph | `resource_graph.py`, `topology_discovery.py` |
| Utilization history | `ResourceUtilizationHistory` + `utilization_trend()` |
| Simple decision layer | `decision_engine.py`, `optimization_actions` (Advisor Phase C) |

## Data model

### Deferred

- `historical_resource_snapshots`

### Phase 1 tables

**`workload_profiles`** — one row per resource, refreshed on score run

**`optimization_scoring`** — one row per resource per `evaluation_date`

### Phase 2 table

**`optimization_rollout_stages`** — staged batches with observation windows

### Extended columns

| Table | Columns |
|-------|---------|
| `resource_dependencies` | `criticality` (per edge) |
| `optimization_actions` | `recommendation_tier`, `overall_score` (nullable) |

## API

| Endpoint | Phase | Access |
|----------|-------|--------|
| `POST /optimize/engine/score` | 1 | Admin |
| `GET /optimize/engine/scoreboard` | 1 | Authenticated |
| `POST /optimize/rollout/plan` | 2 | Admin |
| `GET /optimize/rollout/stages` | 2 | Authenticated |
| `POST /optimize/rollout/stages/{id}/start` | 2 | Admin |
| `POST /optimize/rollout/stages/{id}/expand` | 2 | Admin |
| `POST /optimize/rollout/stages/{id}/rollback` | 2 | Admin |
| `GET /optimize/resources/{resource_id}/analysis` | 4 | Authenticated |
| `GET /optimize/trends` | 4 | Authenticated |

## Phase 1 acceptance criteria

- [x] Spec decisions documented (weights, tiers, tags, table deferrals)
- [x] `workload_profiles` + `optimization_scoring` models + migrations
- [x] `workload_profiler`, `dependency_analyzer`, `trend_analyzer`, `advanced_engine`
- [x] `POST /optimize/engine/score`, `GET /optimize/engine/scoreboard`
- [x] Unit tests for tier boundaries and composite scoring
- [x] Advisory only — no auto-execution

## Implementation notes (Phase 1)

- `app/optimizer/scoring_weights.py` — weights + tier thresholds + tag keys
- `app/optimizer/workload_profiler.py` — persists `workload_profiles`
- `app/optimizer/dependency_analyzer.py` — blast radius + criticality
- `app/optimizer/trend_analyzer.py` — wraps `utilization_history` + `cost_by_resource`
- `app/optimizer/advanced_engine.py` — 5-dimension scoring
- `app/advanced_scoring.py` — orchestration + scoreboard list
- `tests/test_advanced_engine.py` — tier + scoring tests

## Out of scope (Phase 1)

- Rollout stages, auto-expand, rollback
- Scoreboard UI
- `historical_resource_snapshots`
- Replacing simple `decision_engine`

## Phase 2–3 acceptance criteria

- [x] `optimization_rollout_stages` model + migration
- [x] `rollout_orchestrator.py` — plan, start, expand, rollback
- [x] Rollout API routes (plan, list, start, expand, rollback)
- [x] `tests/test_rollout_orchestrator.py`
- [x] `/optimize/scoreboard` page + `MultiFacetScore` component
- [x] Scoreboard API client + `useOptimizationScoreboard` hook
- [x] Scheduler integration for rollout observation checks (`ROLLOUT_OBSERVATION_HOURS`, default 6h)
- [x] `/optimize/rollout-monitor` UI

## Phase 4 acceptance criteria

- [x] `GET /optimize/trends` — tier counts, rollout health, savings summary
- [x] `GET /optimize/resources/analysis` — workload, scorecard, dependencies, trends
- [x] `POST /optimize/rollout/observe` — manual observation check
- [x] Rollout observation scheduler loop in `operations_scheduler.py`
- [x] `/optimize/rollout-monitor` page with start/expand/rollback
- [x] `AdvancedResourceSection` in resource drawer
- [x] Dashboard advanced optimization trends widget
- [x] `tests/test_optimization_trends.py`

## Implementation notes

- Phase 1 started Jul 3, 2026 on `dev-slot`
- Phase 2–3: `app/optimizer/rollout_orchestrator.py`, `frontend/src/pages/OptimizationScoreboard.jsx`
- No Redis; parallel scoring via `ThreadPoolExecutor` when resource count > 50
- Scores conservative when `insufficient_history` on utilization trends
- Rollout expand checks CPU regression (>25% vs baseline) before completing stage
