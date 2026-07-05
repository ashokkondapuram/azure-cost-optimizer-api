# Azure Advisor integration

**Status:** Draft — Phase B complete (read-only UI)  
**Author:** Engineering  
**Date:** Jul 3, 2026  
**Branch:** `dev-slot`  
**Related:** [`specs/approved/2026-06-unified-optimization-engine.md`](../approved/2026-06-unified-optimization-engine.md)

## Problem statement

CostOptimizeRecommender combines cost export, Azure Monitor metrics, and inventory to produce optimization findings. Azure Advisor adds curated recommendations across cost, performance, reliability, and security. Without Advisor, the app may propose changes that conflict with Azure-native guidance or miss reservation and reliability signals.

**Goal:** Ingest Azure Advisor recommendations, persist snapshots, and (in later phases) synthesize a single recommended action per resource with confidence scoring alongside existing engine findings.

## Proposed solution

1. **Phase A (backend):** Advisor API client, `advisor_recommendations` table, sync + list endpoints. No UI.
2. **Phase B (read-only UI):** Badges and drawer sections showing Advisor data.
3. **Phase C (workflow):** `optimization_actions` table, approval flow, actions page.
4. **Phase D:** Decision engine, `monitor_summary`, dashboard widgets, automation guardrails.

## What stays intact

- Existing `optimization_findings`, cost/metrics/inventory sync, `/advisor` dashboard alias (internal findings — **not** Azure Advisor).
- Auth, scheduler patterns, `ResourceInsightDrawer` shell.

## Data model (phased)

| Table | Phase | Purpose |
|-------|-------|---------|
| `advisor_recommendations` | A | Snapshot of Azure Advisor API rows |
| `monitor_summary` | D | 7d/30d metric aggregates for decision rules |
| `optimization_actions` | C | Synthesized action per resource + workflow |
| `optimization_findings` + FKs | C | Link findings to Advisor + actions |

## API (phased)

| Endpoint | Phase | Access |
|----------|-------|--------|
| `POST /optimize/advisor/generate` | A | Admin — trigger Advisor generate |
| `POST /optimize/advisor/sync` | A | Admin — list + upsert snapshots |
| `GET /optimize/advisor/list` | A | Authenticated — DB-backed list |
| `POST /optimize/actions/decide` | C | Admin — decision engine |
| `PATCH /optimize/actions/{id}` | C | User — approve/reject/defer |

**Naming:** New routes live under `/optimize/advisor/*`. Existing `GET /advisor` remains internal findings for backward compatibility.

## Phase A acceptance criteria

- [x] `AdvisorRecommendation` model + `migrate_schema` creates table on startup
- [x] `AdvisorClient` lists/generates via ARM (`Microsoft.Advisor`, api-version `2023-01-01`)
- [x] `POST /optimize/advisor/sync` upserts rows idempotently (`subscription_id` + `recommendation_id`)
- [x] `GET /optimize/advisor/list` returns paginated stored recommendations with category filter
- [x] `POST /optimize/advisor/generate` triggers Azure generate (admin)
- [x] Unit tests for normalization and DB upsert

## Phase B acceptance criteria

- [x] Advisor components (`AdvisorRecommendationBadge`, `AdvisorDetailPanel`, `AdvisorCategoryIcon`, `AdvisorTableCell`)
- [x] `useAdvisorIndex` hook + `/optimize/advisor/list` API client
- [x] Advisor column on resource inventory tables (`ResourceList`, VMs, disks, AKS)
- [x] Azure Advisor section in `ResourceInsightDrawer`
- [ ] Dashboard widget (deferred to Phase D)

## Out of scope (Phase B)

- Decision engine, `optimization_actions`, approval workflow, scheduler worker, dashboard widget.

## Open questions

1. **Permissions:** Confirm app registration has Advisor read on subscriptions (same ARM scope as inventory).
2. **`monitor_summary`:** New table vs extend `resource_utilization_history` — decide in Phase D.
3. **Dismiss sync:** Call Azure dismiss API vs app-only override — Phase C.

## Implementation notes

- Phase A started Jul 3, 2026 on `dev-slot`.
- HTTP via `app/http_client.py` (no new Azure SDK package).
- Phase A delivered: `app/azure_advisor.py`, `app/advisor_sync.py`, `AdvisorRecommendation` model, three API routes under `/optimize/advisor/*`, `tests/test_advisor_sync.py`.
- Phase B delivered: `frontend/src/components/advisor/*`, `useAdvisorIndex`, advisor column on inventory tables, drawer section.
- Existing `GET /advisor` unchanged (internal optimization findings).
