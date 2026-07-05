# Backend

## Overview
Python FastAPI application (`app/main.py`) integrating Azure ARM/Cost APIs, PostgreSQL persistence, and the optimization engine.

## Security model

- **Auth:** JWT middleware (`app/middleware/app_auth.py`); roles `admin` and `viewer`.
- **Subscription allowlist:** `ensure_subscription_known()` only accepts subscriptions with synced operational data (resource/cost/finding rows), not catalog-only cache entries.
- **Live ARM:** Admin-only via `_require_admin_live_arm()` or `source=live` on list endpoints.
- **Metrics fan-out:** `/metrics/subscription` and `/metrics/by-type` are admin-only.
- **Findings status:** Viewers may acknowledge or ignore; resolve/reopen requires admin.

## Key modules

| Module | Role |
|--------|------|
| `main.py` | Routes, request validation, orchestration |
| `azure_resources.py` / `azure_cost.py` | Azure API clients |
| `db_sync.py` | Inventory + cost sync into PostgreSQL |
| `analysis/orchestrator.py` | DB-first analysis, persists findings |
| `batch_analyzer.py` | Background analysis jobs |
| `optimizer/` | Rule engine and resource sub-engines |
| `resource_store.py` | DB-first inventory reads |
| `validators.py` | Subscription and input validation |

## Analysis

- `POST /optimize/analyze` queues a background job; honors optional `components` for scoped runs.
- Cost-export rules merge on every run (including scoped analysis).
- Job progress shows a single step label (full or scoped component names).

## Inventory

Resource list endpoints default to DB reads (`_db_or_live`). Canonical types map through `sync_scope.py` and `resource_store.RESOURCE_COUNTS_KEYS`.

## Kubernetes agent

- POST ingest endpoints require the agent API key.
- GET snapshot/list endpoints accept agent key **or** signed-in app users.

See also: [api-reference.md](./api-reference.md), [security.md](./security.md).
