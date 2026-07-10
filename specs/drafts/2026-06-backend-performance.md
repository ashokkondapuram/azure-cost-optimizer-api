# Backend performance improvements

**Status:** Draft (Phase 1 implemented Jul 7, 2026)  
**Date:** Jun 30, 2026

## Implemented

| ID | Change | Status |
|----|--------|--------|
| P0-1 | Lowercase finding status + index-friendly filters | Done |
| P0-2 | Composite indexes on `resource_snapshots` | Done (migration) |
| P0-3 | Lazy list payloads (`include_properties=false` default) | Done |
| P0-4 | `Cache-Control` middleware on GET routes | Done |
| P0-5 | Shared cost map + TTL cache per subscription | Done |
| P1-4 | `is_cost_export_only` column replaces JSON LIKE scan | Done |
| P1-5 | Parallel K8s + Azure Monitor metric loading | Done |
| P2-1 | Deferred large JSON columns on `ResourceSnapshot` | Done |
| P2-2 | In-process TTL cache (cost map, resource counts) | Done |
| **P1-1a** | **DB-level pagination for `list_billed_resources_page`** | **Done (Jul 7, 2026)** |
| **P1-1b** | **LIMIT+1 pagination + cached totals in `get_resources_db_page`** | **Done (Jul 7, 2026)** |
| **P1-1c** | **Unified `cost_overlays` cache (MTD + lifetime + MoM)** | **Done (Jul 7, 2026)** |
| **P1-1d** | **Cached `subscription_billing_currency` (eliminates redundant queries)** | **Done (Jul 7, 2026)** |
| **P1-1e** | **Single-query MoM delta map (replaces 2× MTD loads)** | **Done (Jul 7, 2026)** |

## Phase 2 (approved, not started)

| ID | Change |
|----|--------|
| P2-a | Cursor-based pagination (API + frontend) |
| P2-b | Dedup-aware page sizing (fetch buffer before dedupe) |
| P2-c | Unified cache metrics |
| P2-d | Consolidate cache invalidation |
| P2-e | Pagination response metadata (`recommended_page_size`) |
| P2-f | Unused import cleanup (`main.py`) |

## Phase 3 (approved, not started)

| ID | Change |
|----|--------|
| P3-a | Sequential month query consolidation |
| P3-b | Batch resource deduplication in sync |
| P3-c | Centralized pagination limits config |
| P3-d | Shared `validate_pagination()` helper |
| P3-e | Cache eviction monitoring |

## API notes

- Resource list endpoints accept `?include_properties=true` for drawer/detail views.
- List responses omit `properties`, `tags`, `skuDetails`, and `analysisSummary` by default.
- Paginated responses: `{ items, total, limit, offset, page_count, has_more }`.
- Billed resource pages use two-bucket DB pagination (cost rows first, then inventory pending cost).

## Verification

- `pytest tests/test_perf_improvements.py`
- `pytest tests/test_billed_resources.py`
- `pytest tests/test_resource_pagination.py`
- Confirm `Cache-Control` on `/resources/vms` responses
- Confirm list payload size reduction without `include_properties`
