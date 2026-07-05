# Backend performance improvements

**Status:** Draft (partial implementation)  
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

## Not yet implemented

| ID | Change |
|----|--------|
| P1-1 | Bulk upsert in sync pipeline |
| P1-2 | Default pagination on all non-paged callers |
| P1-3 | SQL window-function deduplication |
| P1-6 | Parallel Azure resource type syncs |
| P2-3 | Streaming inventory load (`yield_per`) |

## API notes

- Resource list endpoints accept `?include_properties=true` for drawer/detail views.
- List responses omit `properties`, `tags`, `skuDetails`, and `analysisSummary` by default.
- Paginated responses unchanged: `{ items, total, limit, offset, has_more }`.

## Verification

- `pytest tests/test_perf_improvements.py`
- Confirm `Cache-Control` on `/resources/vms` responses
- Confirm list payload size reduction without `include_properties`
