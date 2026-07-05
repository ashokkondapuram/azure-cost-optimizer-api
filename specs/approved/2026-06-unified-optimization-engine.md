# Unified Cost + Performance Optimization Engine

**Status:** Approved — implementation in progress  
**Author:** Engineering  
**Date:** Jun 30, 2026  
**Branch:** `dev-slot`

## Problem statement

CostOptimizeRecommender syncs Azure inventory, analyzes cost/utilization, and surfaces recommendations. The original engine was rule-based on 7-day averages with sequential sub-engines, per-row DB sync, and a UI lacking bulk actions, real-time feedback, and workload-aware insight.

**Hard constraint:** No new external services (no Redis, no message broker). All concurrency uses stdlib `ThreadPoolExecutor`; all caching stays in-process.

## Phases (independently shippable)

| Phase | Focus |
|-------|--------|
| 1 | Backend speed — sync, analysis, indexes, cache |
| 2 | Engine intelligence — peaks, workload class, correlation, anomalies |
| 3 | Time-series — utilization history, forecasting, closed-loop execution |
| 4 | UI/UX — bulk actions, SSE, charts, accessibility |

---

## Implementation audit (Jun 30, 2026)

### Phase 1 — Backend speed

| Item | Status | Notes |
|------|--------|-------|
| 1.1 Bulk upsert | **Done** | `bulk_resource_upsert.py`, `_bulk_sync_pick_properties`, all dedicated sync types + generic ARM |
| 1.2 Parallel ARM fetch | **Done** | `parallel_arm_sync.py`, `db_sync_parallel.py` — compute trio + 20 types in parallel |
| 1.3 Parallel sub-engines | **Done** | `resource_engines/registry.py` |
| 1.4 httpx pooling | **Done** | `http_client.py` HTTP/2 + connection pool |
| 1.5 Query/index fixes | **Done** | Lowercase status, composite indexes, `is_cost_export_only`, JSONB/GIN |
| 1.6 Lazy load / cache / headers | **Done** | `deferred()` columns, `include_properties=false`, `perf_cache` wired, `Cache-Control` + **ETag** |

### Phase 2 — Engine intelligence

| Item | Status | Notes |
|------|--------|-------|
| 2.1 Peak metrics | **Done** | Azure `Maximum` → `max_cpu_pct` etc.; p95/p99 not implemented (by design) |
| 2.2 Workload classifier | **Done** | `workload_classifier.py` wired into VM downsize gates via `downsize_allowed_for_workload` |
| 2.3 Correlation / bottlenecks | **Done** | `resource_graph.py`, `VM_DISK_BOTTLENECK`, `VM_NETWORK_BOTTLENECK` |
| 2.4 AKS consolidation | **Done** | `AKS_POOL_CONSOLIDATION` |
| 2.5 Cost anomaly | **Done** | `cost/anomaly/`, `COST_SPIKE_DETECTED` |
| 2.6 RI + Savings Plan | **Done** | 28-day stability + 4-way comparison |
| 2.7 Action chains | **Done** | `assign_action_chains()`, DB columns |

### Phase 3 — Time-series

| Item | Status | Notes |
|------|--------|-------|
| 3.1 Utilization history | **Done** | `ResourceUtilizationHistory`, persist on analysis |
| 3.2 Demand forecasting | **Done** | `demand_forecaster.py` merged into orchestrator `utilization_trends` |
| 3.3 Execution tracking | **Done** | `RecommendationExecution`, execute/validate APIs, closed-loop escalation on re-analysis, UI "Mark applied" |

### Phase 4 — UI/UX

| Item | Status | Notes |
|------|--------|-------|
| Bulk actions + undo toast | **Done** | Recommendations page |
| Command palette (Cmd+K) | **Done** | |
| Filter presets | **Done** | `useFilterPresets.js` |
| SSE job progress | **Done** | `GET /events/jobs/{sub}` |
| MTD vs last month KPI | **Done** | Dashboard portal |
| Cost period comparison | **Done** | Cost Explorer |
| Interactive charts | **Done** | Recharts Brush + toggles |
| Mobile card view | **Done** | `ResourceList.jsx` |
| CSS accessibility | **Done** | Dark vars, focus rings, z-index ladder |
| New finding types in UI | **Done** | Chain step badge, workload/type badges, rule labels |
| Findings page bulk actions | **Out of scope** | Bulk on Recommendations only (same API) |

---

## Key files

| Area | Files |
|------|-------|
| Sync speed | `app/db_sync.py`, `app/db_sync_parallel.py`, `app/bulk_resource_upsert.py` |
| Analysis speed | `app/optimizer/resource_engines/registry.py` |
| Cache / ETag | `app/perf_cache.py`, `app/http_cache.py` |
| Engine intelligence | `app/optimizer/workload_classifier.py`, `app/analysis/orchestrator.py` |
| Closed-loop | `app/recommendation_execution.py` |
| UI | `frontend/src/components/RecommendationDetailCard.jsx`, `frontend/src/index.css` |

## Dependencies

`httpx[http2]`, `cachetools`, `numpy` (in `requirements.txt`)

## Verification

1. `pytest tests/` — green
2. Full sync uses bulk upsert + parallel fetch for all dedicated types
3. Bursty VM not flagged when peak exceeds threshold; `workload_class` in evidence
4. `chain_id` / `chain_step` in findings API; UI shows step badge
5. Mark applied → `RecommendationExecution` row; re-analysis escalates persistent findings
6. `ETag` + `If-None-Match` returns 304 on unchanged GET responses
7. Dark mode, keyboard focus, 375px single-column grid

## Out of scope

- External cache (Redis)
- True p95/p99 percentiles (Azure Maximum used as peak proxy)
- Findings page bulk UI (API exists; Recommendations has UI)
